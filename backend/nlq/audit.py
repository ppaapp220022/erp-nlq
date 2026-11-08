"""감사 기록 (M6). execute()가 DB에 닿는 시도마다 한 줄씩 남긴다 (docs/adr/0006-audit-log.md).

    {"ts": "...", "uid": 7, "enforce": "guard", "outcome": "ok", "sql": "SELECT ... WHERE name = '?'",
     "rows": 3, "truncated": false, "ms": 12}

누가(Odoo uid), 언제, 어떤 SQL을, 어떤 방식으로 실행했고 어떻게 끝났는지를 남긴다. 개인정보는 남기지 않는다(절대 규칙 6).
- 질문은 남기지 않는다. 자유 텍스트라 고객 이름 등을 걸러 낼 방법이 없다.
- SQL의 문자열 리터럴은 '?'로 바꾼다(`WHERE p.name = '김철수'`). 해석하지 못한 SQL은 남기지 않는다.
- 결과 값과 오류 문구는 남기지 않는다. DB 오류 첫 줄에는 행의 값이 섞일 수 있다. 오류는 종류만 남긴다.
- 사용자는 login 대신 Odoo uid다. login이 이메일인 Odoo 설정이 흔하다.
기록하지 못하면 결과를 돌려주지 않는다(실패 시 닫힘). 파일은 NLQ_AUDIT_LOG, 기본 logs/audit.jsonl(git 제외).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.dialects.postgres import Postgres
from sqlglot.errors import SqlglotError

from nlq.settings import ROOT, setting

OUTCOMES = ("ok", "guard_rejected", "timeout", "error")

# 값이 들어가는 문자열 표기: '...', $$...$$, E'...', x'...', b'...', U&'...', N'...'
STRINGS = (exp.RawString, exp.ByteString, exp.HexString, exp.BitString, exp.UnicodeString, exp.National)
MASK = "?"

_lock = threading.Lock()  # 평가는 여러 스레드에서 execute()를 부른다


class AuditError(RuntimeError):
    """감사 기록을 남기지 못했다. execute()는 결과를 돌려주지 않는다."""


def log_path() -> Path:
    return Path(setting("NLQ_AUDIT_LOG", str(ROOT / "logs" / "audit.jsonl")))


def mask_sql(sql: str) -> str | None:
    """문자열 리터럴을 '?'로 바꾼 SQL. 주석은 버린다. 해석하지 못하면 None(원문을 남기지 않는다)."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
        if not statements:
            return None
        masked = "; ".join(_masked(tree).sql(dialect="postgres", comments=False) for tree in statements)
    except (SqlglotError, RecursionError):
        return None
    return masked if _only_masked_strings(masked) else None


def _masked(tree: exp.Expression) -> exp.Expression:
    for node in list(tree.walk()):
        if isinstance(node, STRINGS) or (isinstance(node, exp.Literal) and node.is_string):
            node.replace(exp.Literal.string(MASK))
        elif isinstance(node, exp.JSONPathKey):  # name->>'ko_KR'
            node.set("this", MASK)
    return tree


def _only_masked_strings(sql: str) -> bool:
    """가린 결과를 다시 토큰으로 나눠, 남은 문자열이 모두 '?'인지 본다. 못 가린 표기가 있으면 기록하지 않는다."""
    try:
        tokens = Postgres().tokenize(sql)
    except SqlglotError:
        return False
    return all(t.text == MASK for t in tokens if "STRING" in t.token_type.name)


def record(
    *, uid: int, enforce: str, sql: str, outcome: str, rows: int | None = None, truncated: bool = False, ms: int
) -> None:
    if outcome not in OUTCOMES:
        raise ValueError(f"모르는 결과: {outcome}")
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
        "uid": int(uid),
        "enforce": enforce,
        "outcome": outcome,
        "sql": mask_sql(sql),
        "rows": rows,
        "truncated": truncated,
        "ms": ms,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    path = log_path()
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
    except OSError as e:
        raise AuditError(f"감사 기록을 남기지 못했다: {type(e).__name__}") from e
