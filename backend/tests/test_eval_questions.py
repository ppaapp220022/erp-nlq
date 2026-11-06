"""평가 문항(eval/questions/) 형식 검사와 정답 SQL 실행 확인.

정답 SQL 실행은 로컬 DB(nlq_readonly)가 있어야 돈다. execute()를 거치므로 guard가 role 사용자의
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


def test_questions_not_in_examples():
    # 절대 규칙 4: 같은 질문을 예시에 두지 않는다
    examples = {load(p)["question"].strip() for p in EXAMPLES}
    assert not examples & {load(p)["question"].strip() for p in QUESTIONS}


@db
@pytest.mark.parametrize("path", QUESTIONS, ids=lambda p: p.stem)
def test_gold_sql_runs(path):
    q = load(path)
    rows = execute(q["gold_sql"], load_users()[q["role"]].user)
    assert rows.rows, "정답이 빈 결과면 아무 SQL이나 맞을 수 있다"
    assert not rows.truncated
