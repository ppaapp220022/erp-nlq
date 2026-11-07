"""화면용 HTTP API (nlq/api.py). generate()·execute()를 감싸기만 하는지, API로도 권한 밖 행이 안 나오는지 본다.

DB가 필요한 테스트는 로컬 DB(nlq_readonly)가 있을 때만 돈다.
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from nlq import Failed, GeneratedSQL, GenerationError, api
from nlq.settings import readonly_conninfo

client = TestClient(api.app)


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


def test_api_reaches_db_only_through_execute():
    # 신뢰 경계: API 모듈은 DB 드라이버나 guard를 직접 쓰지 않는다.
    source = Path(api.__file__).read_text()
    assert "psycopg" not in source
    assert "nlq.guard" not in source and "nlq.execute" not in source


def test_users_lists_login_and_role_only():
    users = client.get("/users").json()
    assert {"login": "sales.kim", "role": "영업 사원"} in users
    assert all(set(u) == {"login", "role"} for u in users)


def test_generate_returns_sql_and_model(monkeypatch):
    seen = {}

    def fake_generate(question, user, failed):
        seen["args"] = (question, user.login)
        seen["failed"] = failed
        return GeneratedSQL(sql="SELECT 1", model="claude-haiku-5-5")

    monkeypatch.setattr(api, "generate", fake_generate)
    res = client.post("/generate", json={"question": "주문 수", "user": "sales.kim"})
    assert res.status_code == 200
    assert res.json() == {"sql": "SELECT 1", "model": "claude-haiku-5-5"}
    assert seen["args"] == ("주문 수", "sales.kim")
    assert seen["failed"] is None


def test_generate_passes_failed_attempt(monkeypatch):
    # 자기 수정: 화면이 실패한 SQL과 오류를 넘기면 generate()에 그대로 간다
    seen = {}

    def fake_generate(question, user, failed):
        seen["failed"] = failed
        return GeneratedSQL(sql="SELECT 2", model="m")

    monkeypatch.setattr(api, "generate", fake_generate)
    failed = {"sql": "SELECT bad", "error": 'column "bad" does not exist'}
    res = client.post("/generate", json={"question": "주문 수", "user": "sales.kim", "failed": failed})
    assert res.status_code == 200
    assert seen["failed"] == Failed(**failed)


def test_generate_error_is_reported(monkeypatch):
    def fail(question, user, failed):
        raise GenerationError("SQL을 만들지 못했다 (stop_reason=refusal)")

    monkeypatch.setattr(api, "generate", fail)
    res = client.post("/generate", json={"question": "주문 수", "user": "sales.kim"})
    assert res.status_code == 502
    assert res.json()["detail"]["kind"] == "generation_error"


@pytest.mark.parametrize("path, body", [("/generate", {"question": "q"}), ("/execute", {"sql": "SELECT 1"})])
def test_unknown_user_is_rejected(path, body):
    res = client.post(path, json={**body, "user": "nobody"})
    assert res.status_code == 400
    assert res.json()["detail"]["kind"] == "unknown_user"


def test_empty_question_is_rejected():
    assert client.post("/generate", json={"question": "", "user": "sales.kim"}).status_code == 422


@db
def test_execute_returns_rows_in_user_scope():
    sql = "SELECT count(*) AS orders FROM sale_order"
    kim = client.post("/execute", json={"sql": sql, "user": "sales.kim"}).json()
    admin = client.post("/execute", json={"sql": sql, "user": "admin"}).json()
    assert kim["columns"] == ["orders"]
    assert 0 < kim["rows"][0][0] < admin["rows"][0][0]
    assert kim["truncated"] is False


@db
def test_execute_cannot_read_other_salesperson_orders():
    # 우회 시도: 영업 사원이 SQL 칸을 고쳐 다른 사원(sales.lee, uid 8)의 주문을 직접 고른다.
    res = client.post("/execute", json={"sql": "SELECT count(*) FROM sale_order WHERE user_id = 8", "user": "sales.kim"})
    assert res.status_code == 200
    assert res.json()["rows"] == [[0]]


@db
@pytest.mark.parametrize(
    "user, sql",
    [
        ("sales.kim", "SELECT * FROM purchase_order"),  # 영업 사원에게 없는 테이블
        ("stock.choi", "SELECT * FROM account_move"),  # 재고 담당은 고객 송장을 못 본다
        ("admin", "SELECT pg_sleep(1)"),  # 허용 목록 밖 함수
        ("admin", "SELECT 1; SELECT 2"),  # 여러 문장
    ],
)
def test_execute_reports_guard_rejection(user, sql):
    res = client.post("/execute", json={"sql": sql, "user": user})
    assert res.status_code == 403
    assert res.json()["detail"]["kind"] == "guard_rejected"


@db
def test_execute_reports_db_error():
    res = client.post("/execute", json={"sql": "SELECT no_such_column FROM sale_order", "user": "admin"})
    assert res.status_code == 400
    assert res.json()["detail"]["kind"] == "execution_error"


def test_cell_converts_db_values_for_json():
    assert api._cell(Decimal("1159.7500")) == 1159.75
    assert api._cell(date(2026, 11, 3)) == "2026-11-03"
    assert api._cell(datetime(2026, 11, 3, 9, 30, 15)) == "2026-11-03 09:30"
    assert api._cell({"en_US": "Office Chair"}) == '{"en_US": "Office Chair"}'
    assert api._cell(None) is None and api._cell(3) == 3 and api._cell("x") == "x"
