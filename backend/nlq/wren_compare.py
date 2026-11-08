"""비교 기준 2: WrenAI에 평가 50문항을 묻고 같은 채점 규칙으로 잰다 (M6).

    uv run --directory backend nlq-eval-wren setup        # WrenAI 프로젝트를 만들고 지식·예시를 넣은 뒤 배포
    uv run --directory backend nlq-eval-wren run          # 50문항
    uv run --directory backend nlq-eval-wren run sales-001

WrenAI는 레포 밖에서 docker로 띄운다(docs/reference/wrenai.md). 이 모듈은 WrenAI의 HTTP API만 부른다.
WrenAI는 nlq_readonly의 멤버 역할(db/wren_role.sql)로 DB에 붙어 같은 테이블을 읽고, 행 범위는 모른다.

문항마다 WrenAI가 낸 SQL을 두 가지로 채점한다. 정답은 둘 다 문항 role 사용자의 범위로 실행한 gold_sql이다.
- scoped: WrenAI SQL을 Postgres 방언으로 바꿔(WrenAI의 dry-plan) 우리 execute()로 role 사용자에게 실행한다.
- direct: WrenAI가 직접 실행한 결과(행 범위 없음).
direct 결과가 같은 SQL의 scoped 결과와 다르면 권한 밖 행이 섞인 것이므로 우회(leak)로 센다.
WrenAI에 넣는 것은 knowledge/와 eval/examples/뿐이다. 평가 문항은 넣지 않는다(CLAUDE.md 절대 규칙 4).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import sqlglot
from sqlglot import exp

from nlq import execute
from nlq.evaluate import AREAS, RESULTS, load_questions
from nlq.identity import TABLES
from nlq.models import ExecutionError, GuardError, Rows
from nlq.retrieve import load_examples
from nlq.scoring import matches
from nlq.settings import ROOT, eval_today, setting
from nlq.users import load_users

KNOWLEDGE = ROOT / "knowledge"
UI = setting("WREN_UI_URL", "http://127.0.0.1:3100")
IBIS = setting("WREN_IBIS_URL", "http://127.0.0.1:8100")
WREN_VERSION = "0.29.2"  # docs/reference/wrenai.md의 compose와 같이 바꾼다
INSTRUCTION_MAX = 1000  # WrenAI 지침 한 개의 최대 길이
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_WAIT_S = 60
# knowledge/tables의 "`열` → [테이블](...)" 표기에서 관계를 읽는다
RELATION = re.compile(r"`(\w+)`(?:\([^)]*\))? → \[(\w+)\]")


def model_name(table: str) -> str:
    """WrenAI가 테이블을 가져올 때 붙이는 모델 이름(스키마_테이블)."""
    return f"public_{table}"


@dataclass
class Result:
    id: str
    area: str
    role: str
    # 둘 다 correct | wrong | generation_error | guard_rejected | execution_error
    scoped: str  # WrenAI SQL을 execute()로 role 사용자에게 실행
    direct: str  # WrenAI가 직접 실행
    # True: 같은 SQL의 직접 실행 결과가 범위를 건 결과와 다르다(범위 밖 행). None: 둘 중 하나가 실행되지 않음
    leak: bool | None = None
    wren_sql: str | None = None
    native_sql: str | None = None
    scoped_error: str | None = None
    direct_error: str | None = None
    seconds: float = 0.0


# --- WrenAI HTTP API ---------------------------------------------------------


class WrenError(Exception):
    pass


def _post(url: str, body: dict, timeout: float = 300) -> object:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error") or detail
        except (ValueError, AttributeError):
            pass
        raise WrenError(f"{e.code} {str(detail)[:500]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise WrenError(str(e)) from e
    try:
        return json.loads(text)
    except ValueError:
        return text


def graphql(query: str, variables: dict | None = None) -> dict:
    answer = _post(f"{UI}/api/graphql", {"query": query, "variables": variables or {}})
    if answer.get("errors"):
        raise WrenError("; ".join(e.get("message", "") for e in answer["errors"]))
    return answer["data"]


def generate_sql(question: str) -> str:
    """질문 → Wren SQL(모델 이름으로 쓴 SQL). wren-ui /api/v1/generate_sql, WrenAI의 질문 파이프라인 전체를 탄다.

    WrenAI는 질문 하나에 LLM을 여러 번, 큰 문맥으로 불러 API 분당 토큰 한도(429)에 자주 걸린다. 한도 오류는
    WrenAI의 실패가 아니므로 쉬었다가 다시 묻는다. 다른 오류는 그대로 생성 실패로 센다.
    """
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            answer = _post(f"{UI}/api/v1/generate_sql", {"question": question})
            break
        except WrenError as e:
            if "rate_limit" not in str(e) or attempt == RATE_LIMIT_RETRIES:
                raise
            time.sleep(RATE_LIMIT_WAIT_S)
    sql = answer.get("sql")
    if not sql:
        raise WrenError("SQL이 없다")
    return sql


def run_sql(sql: str) -> Rows:
    """WrenAI가 직접 실행한다(wren-ui /api/v1/run_sql). 행 수 제한은 execute()와 같은 1,000행."""
    answer = _post(f"{UI}/api/v1/run_sql", {"sql": sql, "limit": 1001})
    columns = answer.get("columns") or []
    names = [c["name"] for c in columns]
    rows = [
        tuple(_typed(r.get(c["name"]), c.get("type", "")) for c in columns) for r in answer.get("records") or []
    ]
    return Rows(columns=names, rows=rows[:1000], executed_sql=sql, truncated=len(rows) > 1000)


def native_sql(sql: str, manifest: str) -> str:
    """Wren SQL을 WrenAI가 DB에 보내는 Postgres SQL로 바꾼다(ibis-server dry-plan).
    generate_sql의 returnSqlDialect와 같은 길이다. 질문을 한 번만 보내려고 따로 부른다."""
    answer = _post(f"{IBIS}/v3/connector/postgres/dry-plan", {"manifestStr": manifest, "sql": sql}, timeout=60)
    if not isinstance(answer, str):
        raise WrenError(f"dry-plan 응답이 SQL이 아니다: {str(answer)[:200]}")
    return _drop_catalog(answer)


def _drop_catalog(sql: str) -> str:
    """dry-plan은 테이블을 erp."public".sale_order처럼 DB 이름까지 붙여 쓴다. guard는 카탈로그가 붙은 이름을
    거부하므로 떼어 낸다. Postgres는 접속한 DB 밖을 가리킬 수 없어 뜻은 같다. 다른 DB 이름이면 그대로 둔다."""
    database = setting("ODOO_DB_NAME", "erp")
    tree = sqlglot.parse_one(sql, read="postgres")
    for table in tree.find_all(exp.Table):
        if table.catalog == database:
            table.set("catalog", None)
    return tree.sql(dialect="postgres")


def deployed_manifest() -> str:
    """마지막 배포의 MDL(base64). /api/v1/models로 배포 해시를 받아 GraphQL getMDL로 꺼낸다."""
    with urllib.request.urlopen(f"{UI}/api/v1/models", timeout=30) as response:
        hash_ = json.loads(response.read())["hash"]
    return graphql("query($h: String!){ getMDL(hash: $h) { mdl } }", {"h": hash_})["getMDL"]["mdl"]


def _typed(value: object, type_name: str) -> object:
    """run_sql은 JSON이라 숫자·날짜가 문자열로 올 수 있다. 열 형으로 되돌려 채점 규칙(scoring.normalize)에 맞춘다."""
    if not isinstance(value, str):
        return value
    t = type_name.lower()
    try:
        if any(k in t for k in ("int", "numeric", "decimal", "double", "float", "real")):
            return Decimal(value)
        if "timestamp" in t:
            return datetime.fromisoformat(value.replace(" UTC", "").removesuffix("Z"))
        if t.startswith("date"):  # Arrow 형 이름: date32[day]
            return date.fromisoformat(value[:10])
    except (InvalidOperation, ValueError):
        pass
    return value


# --- setup: WrenAI에 넣는 것 ------------------------------------------------


def _body(path) -> str:
    """앞머리(---)를 뗀 마크다운 본문."""
    text = path.read_text()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.strip()


def _chunks(text: str, limit: int = INSTRUCTION_MAX) -> list[str]:
    """지침 길이 제한에 맞게 문단 단위로 나눈다."""
    chunks, current = [], ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def instructions() -> list[str]:
    """전역 지침: 오늘 날짜(eval/config.yaml), knowledge/의 함정·흐름·지표 문서."""
    today = eval_today()
    rules = [
        f"오늘은 {today}이다. CURRENT_DATE, now() 대신 DATE '{today}'를 쓴다. "
        f'"이번 달", "지난주" 같은 표현도 이 날짜를 기준으로 푼다.',
        "모델 이름은 Odoo 테이블 이름 앞에 public_을 붙인 것이다(sale_order → public_sale_order). "
        "지침과 설명에 나오는 테이블 이름은 그 모델을 가리킨다.",
    ]
    for folder in ("pitfalls", "flows", "metrics"):
        for path in sorted((KNOWLEDGE / folder).glob("*.md")):
            rules += _chunks(f"[{folder}/{path.name}]\n{_body(path)}")
    return rules


def relations(models: dict[str, dict]) -> list[dict]:
    """knowledge/tables 문서가 적은 "`열` → [테이블]" 연결을 다대일 관계로 만든다."""
    found = []
    for path in sorted((KNOWLEDGE / "tables").glob("*.md")):
        table = path.stem
        for column, target in RELATION.findall(_body(path)):
            source, dest = models.get(model_name(table)), models.get(model_name(target))
            if not source or not dest or column not in source["fields"] or "id" not in dest["fields"]:
                continue
            found.append({
                "fromModelId": source["id"], "fromColumnId": source["fields"][column],
                "toModelId": dest["id"], "toColumnId": dest["fields"]["id"], "type": "MANY_TO_ONE",
            })
    return found


def to_wren_sql(sql: str) -> str:
    """eval/examples의 SQL(테이블 이름)을 Wren SQL(모델 이름)로 바꾼다. 별칭이 없으면 테이블 이름을 별칭으로 남겨
    sale_order.id 같은 열 참조가 그대로 맞게 한다."""
    tree = sqlglot.parse_one(sql, read="postgres")
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if table.name in TABLES and table.name not in ctes and not table.db:
            if not table.alias:
                table.set("alias", exp.TableAlias(this=exp.to_identifier(table.name)))
            table.set("this", exp.to_identifier(model_name(table.name)))
    return tree.sql(dialect="postgres")


def setup(resume: bool = False) -> int:
    """WrenAI 프로젝트를 새로 만든다. 데이터 소스 → 테이블 14개 → 관계 → 설명 → 배포 → 지침 → 예시.

    resume이면 배포까지는 건너뛰고 지침·예시만 넣는다. wren-ui는 색인을 28초만 기다려 배포가 실패로 남는데,
    색인이 끝난 뒤 배포 기록을 고치고 이어서 넣을 때 쓴다(docs/reference/wrenai.md "셋업에서 막힌 것").
    """
    if not resume:
        _create_project()
    return _add_knowledge()


def _create_project() -> None:
    password = setting("WREN_DB_PASSWORD") or setting("NLQ_RO_PASSWORD")
    graphql("mutation { resetCurrentProject }")
    graphql(
        "mutation($d: DataSourceInput!){ saveDataSource(data: $d) { type } }",
        {"d": {"type": "POSTGRES", "properties": {
            "displayName": "erp", "host": setting("WREN_DB_HOST", "db"), "port": 5432,
            "database": setting("ODOO_DB_NAME", "erp"), "user": setting("WREN_DB_USER", "nlq_wren"),
            "password": password, "ssl": False,
        }}},
    )
    tables = [t["name"] for t in graphql("{ listDataSourceTables { name } }")["listDataSourceTables"]]
    print(f"테이블 {len(tables)}개: {', '.join(sorted(tables))}", file=sys.stderr)
    graphql("mutation($d: SaveTablesInput!){ saveTables(data: $d) }", {"d": {"tables": tables}})

    listed = graphql("{ listModels { id referenceName fields { id referenceName } } }")["listModels"]
    models = {
        m["referenceName"]: {"id": m["id"], "fields": {f["referenceName"]: f["id"] for f in m["fields"]}} for m in listed
    }
    found = relations(models)
    graphql("mutation($d: SaveRelationInput!){ saveRelations(data: $d) }", {"d": {"relations": found}})
    print(f"관계 {len(found)}개 (knowledge/tables의 → 표기)", file=sys.stderr)

    described = 0
    for path in sorted((KNOWLEDGE / "tables").glob("*.md")):
        model = models.get(model_name(path.stem))
        if model:
            graphql(
                "mutation($w: ModelWhereInput!, $d: UpdateModelMetadataInput!){ updateModelMetadata(where: $w, data: $d) }",
                {"w": {"id": model["id"]}, "d": {"displayName": path.stem, "description": _body(path)}},
            )
            described += 1
    print(f"모델 설명 {described}개 (knowledge/tables)", file=sys.stderr)
    graphql("mutation($d: UpdateCurrentProjectInput!){ updateCurrentProject(data: $d) }", {"d": {"language": "KO"}})
    deployed = graphql("mutation { deploy(force: true) }")["deploy"]
    if deployed.get("status") != "SUCCESS":
        raise WrenError(f"배포 실패: {deployed}. 색인이 끝난 뒤 배포 기록을 고치고 setup --resume")


def _add_knowledge() -> int:
    rules = instructions()
    for rule in rules:
        _post(f"{UI}/api/v1/knowledge/instructions", {"instruction": rule, "isGlobal": True})
    print(f"전역 지침 {len(rules)}개 (오늘 날짜, 모델 이름, knowledge/ 함정·흐름·지표)", file=sys.stderr)

    added, failed = 0, []
    for example in load_examples():
        try:
            _post(f"{UI}/api/v1/knowledge/sql_pairs", {"question": example.question, "sql": to_wren_sql(example.sql)})
            added += 1
        except WrenError as e:
            failed.append(f"{example.id}: {e}")
    print(f"SQL 예시 {added}개 (eval/examples)" + "".join(f"\n  실패 {f}" for f in failed), file=sys.stderr)
    # WrenAI 엔진이 거부한 예시(jsonb ->> 등)는 넣지 못한 채로 둔다. 결과 표에 개수를 적는다
    return 0


# --- 평가 --------------------------------------------------------------------


def _status(error: Exception) -> str:
    return "guard_rejected" if isinstance(error, GuardError) else "execution_error"


def run_one(q: dict, manifest: str, wren_sql: str | None = None) -> Result:
    """wren_sql이 있으면(--rescore) WrenAI에 다시 묻지 않고 그 SQL을 채점만 한다."""
    user = load_users()[q["role"]].user
    start = time.monotonic()
    result = Result(id=q["id"], area=q["area"], role=q["role"], scoped="generation_error", direct="generation_error")
    gold = execute(q["gold_sql"], user)
    try:
        result.wren_sql = wren_sql or generate_sql(q["question"])
    except WrenError as e:
        result.scoped_error = result.direct_error = str(e)
        result.seconds = round(time.monotonic() - start, 1)
        return result

    scoped = direct = None
    try:
        result.native_sql = native_sql(result.wren_sql, manifest)
        scoped = execute(result.native_sql, user)
        result.scoped = "correct" if matches(gold, scoped, q["order_matters"]) else "wrong"
    except (ExecutionError, WrenError) as e:
        result.scoped, result.scoped_error = _status(e), str(e)
    try:
        direct = run_sql(result.wren_sql)
        result.direct = "correct" if matches(_json_text(gold), direct, q["order_matters"]) else "wrong"
    except WrenError as e:
        result.direct, result.direct_error = "execution_error", str(e)
    if scoped is not None and direct is not None:
        # 같은 SQL을 범위를 걸고/안 걸고 실행한 결과가 다르면 범위 밖 행이 섞인 것이다
        result.leak = not matches(_json_text(scoped), direct, order_matters=False)
    result.seconds = round(time.monotonic() - start, 1)
    return result


def _json_text(rows: Rows) -> Rows:
    """execute()는 jsonb를 dict로, WrenAI는 JSON 문자열로 돌려준다. 직접 실행 결과와 비교할 때만 문자열로 맞춘다."""
    def text(value: object) -> object:
        return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value

    return replace(rows, rows=[tuple(text(v) for v in row) for row in rows.rows])


def summarize(results: list[Result]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        for key in (r.area, "전체"):
            s = summary[key]
            s["total"] += 1
            s[f"scoped_{r.scoped}"] += 1
            s[f"direct_{r.direct}"] += 1
            s["leak"] += bool(r.leak)
            # 직접 실행은 정답이 아닌데 범위를 건 실행은 정답: 범위가 빠져 틀린 문항
            s["fixed_by_scope"] += r.direct != "correct" and r.scoped == "correct"
    return {k: dict(v) for k, v in summary.items()}


def format_summary(summary: dict[str, dict[str, int]]) -> str:
    lines = [
        "| 영역 | 문항 | execute() 정답 | 직접 실행 정답 | 우회(범위 밖 행) | 생성 실패 | guard 거부 | 실행 오류(execute/직접) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for area in [a for a in AREAS if a in summary] + ["전체"]:
        s = summary[area]
        lines.append(
            f"| {area} | {s['total']} | {s.get('scoped_correct', 0)} | {s.get('direct_correct', 0)} | {s.get('leak', 0)} "
            f"| {s.get('scoped_generation_error', 0)} | {s.get('scoped_guard_rejected', 0)} "
            f"| {s.get('scoped_execution_error', 0)}/{s.get('direct_execution_error', 0)} |"
        )
    return "\n".join(lines)


def _rescored(old: dict, q: dict, manifest: str) -> Result:
    if not old["wren_sql"]:
        return Result(**{k: v for k, v in old.items()})
    result = run_one(q, manifest, old["wren_sql"])
    result.seconds = old["seconds"]
    return result


def evaluate(ids: list[str], jobs: int, rescore: str | None = None) -> int:
    questions = load_questions(ids or None)
    saved: dict[str, dict] = {}
    if rescore:
        # 채점 규칙만 고쳤을 때: 저장한 Wren SQL을 다시 실행해 채점한다. 생성 실패였던 문항은 그대로 둔다
        saved = {r["id"]: r for r in json.loads(open(rescore).read())["results"]}
    manifest = deployed_manifest()
    model = setting("WREN_MODEL", "claude-haiku-5-5")
    print(f"WrenAI {WREN_VERSION}, 모델 {model}(WrenAI config.yaml), 문항 {len(questions)}개", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        results = list(pool.map(lambda q: _rescored(saved[q["id"]], q, manifest) if rescore else run_one(q, manifest), questions))
    for r in results:
        error = r.scoped_error or r.direct_error
        detail = f"  {error[:160]}" if error else ""
        print(f"{r.id:<14} execute {r.scoped:<16} 직접 {r.direct:<16} {'우회' if r.leak else '':<4} {r.seconds:>5}s{detail}",
              file=sys.stderr)
    summary = summarize(results)
    record = {
        "system": f"WrenAI {WREN_VERSION}",
        "model": model,
        "today": eval_today(),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-wrenai-{WREN_VERSION}-{model}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(format_summary(summary))
    print(f"\n결과: {path.relative_to(ROOT)}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nlq-eval-wren", description="비교 기준 2: WrenAI로 평가 문항 채점")
    parser.add_argument("command", choices=("setup", "run"))
    parser.add_argument("ids", nargs="*", help="돌릴 문항 id. 없으면 전체 (run)")
    # WrenAI가 질문을 한 번에 하나씩 처리하는 편이라 동시 실행을 적게 둔다
    parser.add_argument("--resume", action="store_true", help="setup: 배포 뒤의 지침·예시만 넣는다")
    parser.add_argument("--rescore", metavar="결과.json", help="run: WrenAI에 다시 묻지 않고 저장한 SQL을 다시 채점")
    parser.add_argument("--jobs", type=int, default=2, help="동시에 보낼 문항 수")
    args = parser.parse_args(argv)
    return setup(args.resume) if args.command == "setup" else evaluate(args.ids, args.jobs, args.rescore)


if __name__ == "__main__":
    sys.exit(main())
