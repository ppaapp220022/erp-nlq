"""평가 문항(eval/questions/)과 예시(eval/examples/)의 형식 검사, SQL 실행 확인, 두 폴더가 겹치지 않는지.

SQL 실행은 로컬 DB(nlq_readonly)가 있어야 돈다. execute()를 거치므로 guard가 role 사용자의
행 범위를 건 결과가 비지 않는지 본다.
"""

import re
from pathlib import Path

import psycopg
import pytest
import yaml

from nlq import execute
from nlq.settings import readonly_conninfo
from nlq.users import load_users

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = sorted((ROOT / "eval" / "questions").glob("*.yaml"))
EXAMPLES = sorted((ROOT / "eval" / "examples").glob("*.yaml"))
AREAS = {"sales": "판매", "purchase": "구매", "stock": "재고", "account": "회계"}
FIELDS = {"id", "area", "role", "question", "gold_sql", "order_matters", "notes"}
EXAMPLE_FIELDS = {"id", "area", "role", "question", "sql", "notes"}
# 질문 글자 2-gram의 Jaccard 유사도가 이 값 이상이면 숫자·이름만 바꾼 질문으로 본다
NEAR_DUPLICATE = 0.5


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


def test_questions_exist():
    assert QUESTIONS


@pytest.mark.parametrize("path", QUESTIONS, ids=lambda p: p.stem)
def test_format(path):
    q = load(path)
    assert set(q) == FIELDS
    assert q["id"] == path.stem
    prefix, _, number = path.stem.partition("-")
    assert re.fullmatch(r"\d{3}", number)
    assert q["area"] == AREAS[prefix]
    assert q["role"] in load_users()
    assert isinstance(q["order_matters"], bool)
    # 날짜는 eval/config.yaml의 today로 푼다. 실행일에 따라 정답이 바뀌면 안 된다
    assert not re.search(r"current_date|now\(\)|current_timestamp", q["gold_sql"], re.I)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_format(path):
    e = load(path)
    assert set(e) == EXAMPLE_FIELDS
    assert e["id"] == f"ex-{path.stem}"
    prefix, _, number = path.stem.partition("-")
    assert re.fullmatch(r"\d{3}", number)
    assert e["area"] == AREAS[prefix]
    assert e["role"] in load_users()
    assert not re.search(r"current_date|now\(\)|current_timestamp", e["sql"], re.I)


def test_examples_cover_every_area():
    assert {load(p)["area"] for p in EXAMPLES} == set(AREAS.values())


def test_questions_not_in_examples():
    # 절대 규칙 4: 같은 질문을 예시에 두지 않는다
    examples = {load(p)["question"].strip() for p in EXAMPLES}
    assert not examples & {load(p)["question"].strip() for p in QUESTIONS}


def _bigrams(text: str) -> set[str]:
    s = re.sub(r"\s+", "", text)
    return {s[i : i + 2] for i in range(len(s) - 1)}


def test_examples_are_not_near_duplicates_of_questions():
    # 숫자·이름만 바꾼 질문도 예시에 두지 않는다(eval/README.md)
    questions = {p.stem: _bigrams(load(p)["question"]) for p in QUESTIONS}
    close = []
    for path in EXAMPLES:
        e = _bigrams(load(path)["question"])
        for stem, q in questions.items():
            if len(e & q) / len(e | q) >= NEAR_DUPLICATE:
                close.append((path.stem, stem))
    assert not close


@db
@pytest.mark.parametrize("path", QUESTIONS, ids=lambda p: p.stem)
def test_gold_sql_runs(path):
    q = load(path)
    rows = execute(q["gold_sql"], load_users()[q["role"]].user)
    assert rows.rows, "정답이 빈 결과면 아무 SQL이나 맞을 수 있다"
    assert not rows.truncated


@db
@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_sql_runs(path):
    e = load(path)
    rows = execute(e["sql"], load_users()[e["role"]].user)
    assert rows.rows, "빈 결과를 내는 예시는 모델에게 맞는 SQL인지 알려 주지 못한다"
    assert not rows.truncated


@db
def test_examples_do_not_reproduce_gold_results():
    # 질문 문장이 달라도 같은 결과를 내는 예시는 정답을 보여 주는 것과 같다
    users = load_users()

    def result(sql: str, role: str) -> list[str]:
        return sorted(map(repr, execute(sql, users[role].user).rows))

    gold = {p.stem: result(q["gold_sql"], q["role"]) for p in QUESTIONS for q in [load(p)]}
    same = [
        (p.stem, stem)
        for p in EXAMPLES
        for e in [load(p)]
        for r in [result(e["sql"], e["role"])]
        for stem, g in gold.items()
        if r == g
    ]
    assert not same
