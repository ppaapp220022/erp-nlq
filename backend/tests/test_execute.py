"""execute()의 실행 안전장치 테스트. 로컬 DB(nlq_readonly)가 있어야 돈다.

DB가 없으면(CI의 checks 등) 건너뛴다. 행 범위(guard)는 M3에서 따로 테스트한다.
"""

import importlib
import time

import psycopg
import pytest

from nlq import ExecutionError, User, execute
from nlq.settings import readonly_conninfo

# nlq 패키지가 execute 함수를 같은 이름으로 내보내므로 모듈은 따로 가져온다.
execute_module = importlib.import_module("nlq.execute")

USER = User(odoo_uid=6, login="demo", company_ids=(1,))


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


@db
def test_select_returns_columns_and_rows():
    rows = execute("SELECT id, name FROM res_company ORDER BY id", USER)
    assert rows.columns == ["id", "name"]
    assert rows.rows[0][0] == 1
    assert not rows.truncated
    assert rows.warnings == [execute_module.NO_ROW_SCOPE]


@db
def test_percent_in_sql_is_not_a_placeholder():
    rows = execute("SELECT count(*) FROM res_partner WHERE name LIKE '%a%'", USER)
    assert rows.rows[0][0] > 0


@db
def test_row_limit_truncates():
    rows = execute(f"SELECT g FROM generate_series(1, {execute_module.MAX_ROWS + 5}) g", USER)
    assert len(rows.rows) == execute_module.MAX_ROWS
    assert rows.truncated


@db
def test_statement_timeout(monkeypatch):
    monkeypatch.setattr(execute_module, "STATEMENT_TIMEOUT_MS", 500)
    start = time.monotonic()
    with pytest.raises(ExecutionError, match="시간 제한"):
        execute("SELECT pg_sleep(5)", USER)
    assert time.monotonic() - start < 3


# 우회 시도. 하나라도 실행되면 실행 안전장치가 뚫린 것이다.
BYPASS = {
    "insert": "INSERT INTO res_company (name) VALUES ('x')",
    "update": "UPDATE sale_order SET user_id = NULL",
    "delete_in_cte": "WITH d AS (DELETE FROM sale_order RETURNING id) SELECT * FROM d",
    "multi_statement": "SELECT 1; SELECT 2",
    "commit_then_write": "SELECT 1; COMMIT; SET default_transaction_read_only = off",
    "set": "SET statement_timeout = 0",
    "create_temp": "CREATE TEMP TABLE t AS SELECT 1",
    "read_write_via_set_config": "SELECT set_config('transaction_read_only', 'off', true)",
    "select_for_update": "SELECT id FROM sale_order FOR UPDATE",
    "copy_program": "COPY (SELECT 1) TO PROGRAM 'id'",
    "ungranted_table": "SELECT * FROM account_move_line",
    "ungranted_column": "SELECT password FROM res_users",
    "catalog_passwords": "SELECT * FROM pg_authid",
    "lo_export": "SELECT lo_export(1, '/tmp/x')",
}


@db
@pytest.mark.parametrize("sql", BYPASS.values(), ids=BYPASS.keys())
def test_bypass_is_rejected(sql):
    with pytest.raises(ExecutionError):
        execute(sql, USER)


@db
def test_timeout_cannot_be_turned_off_inside_query(monkeypatch):
    monkeypatch.setattr(execute_module, "STATEMENT_TIMEOUT_MS", 500)
    with pytest.raises(ExecutionError, match="시간 제한"):
        execute("SELECT set_config('statement_timeout', '0', true), pg_sleep(5)", USER)


def test_refuses_superuser(monkeypatch):
    class FakeConn:
        read_only = False
        closed = False

        def execute(self, *_):
            return self

        def fetchone(self):
            return (True, False)  # rolsuper, rolbypassrls

        def close(self):
            self.closed = True

    fake = FakeConn()
    monkeypatch.setattr(execute_module, "readonly_conninfo", lambda: {})
    monkeypatch.setattr(psycopg, "connect", lambda **_: fake)
    with pytest.raises(RuntimeError, match="superuser"):
        execute("SELECT 1", USER)
    assert fake.closed
