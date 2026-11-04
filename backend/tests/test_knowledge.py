import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "knowledge"
TYPES = {"table", "metric", "flow", "pitfall"}
DOCS = sorted(p for p in KNOWLEDGE.rglob("*.md") if p.name != "README.md")


def allowed_tables() -> set[str]:
    # 질의 계층이 읽을 수 있는 상한. 문서가 이 밖의 테이블을 가르치면 생성 SQL이 실행 단계에서 막힌다.
    sql = (ROOT / "db" / "readonly_role.sql").read_text()
    tables = set()
    for names in re.findall(r"^GRANT SELECT(?: \([^)]*\))? ON ([\w, ]+?) TO", sql, re.M):
        tables |= {n.strip() for n in names.split(",")}
    return tables


def front_matter(path: Path) -> dict[str, str | list[str]]:
    text = path.read_text()
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path}: 앞머리 없음"
    meta: dict[str, str | list[str]] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        value = value.split("#")[0].strip()
        if value.startswith("["):
            meta[key.strip()] = [v.strip() for v in value.strip("[]").split(",") if v.strip()]
        else:
            meta[key.strip()] = value
    return meta


def test_docs_exist():
    assert DOCS


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(KNOWLEDGE)))
def test_front_matter(path):
    meta = front_matter(path)
    assert meta.get("type") in TYPES
    assert meta.get("title")
    assert meta.get("tables"), "역할로 거르려면 tables가 필요하다"
    assert set(meta["tables"]) <= allowed_tables()


@pytest.mark.parametrize("path", DOCS, ids=lambda p: str(p.relative_to(KNOWLEDGE)))
def test_relative_links_resolve(path):
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
        if target.startswith(("http://", "https://")):
            continue
        assert (path.parent / target.split("#")[0]).exists(), f"{path.name}: {target}"


def test_every_allowed_table_has_a_doc():
    documented = {front_matter(p)["title"].split()[0] for p in DOCS if front_matter(p)["type"] == "table"}
    assert documented == allowed_tables()


def test_no_eval_question_in_knowledge():
    # 절대 규칙 4: 평가 문항이 프롬프트에 들어가면 점수가 부풀려진다.
    knowledge = "\n".join(p.read_text() for p in DOCS)
    for q in (ROOT / "eval" / "questions").glob("*.yaml"):
        for question in re.findall(r"^question:\s*(.+)$", q.read_text(), re.M):
            assert question.strip() not in knowledge, q.name
