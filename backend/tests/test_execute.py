"""execute()의 실행 안전장치 테스트. 로컬 DB(nlq_readonly)가 있어야 돈다.

DB가 없으면(CI의 checks 등) 건너뛴다. guard는 test_guard.py에서 테스트한다.
여기서는 guard를 끈 채로(no_guard) 실행 안전장치만 본다. guard가 뚫려도 이 층이 막아야 한다.
"""

import importlib
import time

import psycopg
import pytest

from nlq import ExecutionError, User, execute
from nlq.settings import readonly_conninfo
from nlq.users import load_users

# nlq 패키지가 execute 함수를 같은 이름으로 내보내므로 모듈은 따로 가져온다.
execute_module = importlib.import_module("nlq.execute")

USER = load_users()["demo"].user


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


# pg_sleep은 실행 권한이 없으므로 계산으로 시간을 끈다. 끝까지 돌면 몇 분 걸린다.
SLOW_SQL = "SELECT count(*) FROM generate_series(1, 10000000000)"


@pytest.fixture
def no_guard(monkeypatch):
    monkeypatch.setattr(execute_module, "guard", lambda sql, user, max_rows: sql)


def test_unknown_user_reads_nothing():
    # users.toml에 없는 사용자는 그룹·테이블이 비어 있어 guard가 거부한다 (실패 시 닫힘)
    with pytest.raises(ExecutionError):
        execute("SELECT id FROM res_company", User(odoo_uid=6, login="x", company_ids=(1,)))


@db
def test_select_returns_columns_and_rows():
    rows = execute("SELECT id, name FROM res_company ORDER BY id", USER)
    assert rows.columns == ["id", "name"]
    assert rows.rows[0][0] == 1
    assert not rows.truncated


@db
def test_percent_in_sql_is_not_a_placeholder():
    rows = execute("SELECT count(*) FROM res_partner WHERE name LIKE '%a%'", USER)
    assert rows.rows[0][0] > 0


@db
def test_row_limit_truncates(no_guard):
    rows = execute(f"SELECT g FROM generate_series(1, {execute_module.MAX_ROWS + 5}) g", USER)
    assert len(rows.rows) == execute_module.MAX_ROWS
    assert rows.truncated


@db
def test_statement_timeout(monkeypatch, no_guard):
    monkeypatch.setattr(execute_module, "STATEMENT_TIMEOUT_MS", 500)
    start = time.monotonic()
    with pytest.raises(ExecutionError, match="시간 제한"):
        execute(SLOW_SQL, USER)
    assert time.monotonic() - start < 3


# 우회 시도. guard 없이도 하나라도 실행되면 실행 안전장치가 뚫린 것이다.
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
def test_bypass_is_rejected(sql, no_guard):
    with pytest.raises(ExecutionError):
        execute(sql, USER)


@db
def test_timeout_cannot_be_turned_off_inside_query(monkeypatch, no_guard):
    monkeypatch.setattr(execute_module, "STATEMENT_TIMEOUT_MS", 500)
    with pytest.raises(ExecutionError, match="permission denied for function set_config"):
        execute(f"SELECT set_config('statement_timeout', '0', true), ({SLOW_SQL})", USER)


# 위험 함수. guard의 함수 허용 목록이 뚫려도 DB가 실행 권한으로 막아야 한다 (db/readonly_role.sql).
DANGEROUS_FUNCTIONS = {
    "set_config": "SELECT set_config('statement_timeout', '0', false)",
    "current_setting": "SELECT current_setting('data_directory')",
    "pg_sleep": "SELECT pg_sleep(0)",
    "pg_sleep_for": "SELECT pg_sleep_for('0 seconds')",
    "pg_sleep_until": "SELECT pg_sleep_until(now())",
    "query_to_xml": "SELECT query_to_xml('SELECT * FROM sale_order', true, false, '')",
    "table_to_xml": "SELECT table_to_xml('sale_order', true, false, '')",
    "database_to_xml": "SELECT database_to_xml(true, false, '')",
    "lo_get": "SELECT lo_get(1)",
    "lo_from_bytea": "SELECT lo_from_bytea(0, 'x')",
    "pg_read_file": "SELECT pg_read_file('/etc/passwd')",
    "pg_read_binary_file": "SELECT pg_read_binary_file('/etc/passwd')",
    "pg_ls_dir": "SELECT pg_ls_dir('.')",
    "pg_stat_file": "SELECT pg_stat_file('.')",
}


@db
@pytest.mark.parametrize("sql", DANGEROUS_FUNCTIONS.values(), ids=DANGEROUS_FUNCTIONS.keys())
def test_dangerous_function_is_denied_by_db(sql, no_guard):
    with pytest.raises(ExecutionError, match="permission denied for function"):
        execute(sql, USER)


@db
def test_no_overload_of_dangerous_functions_is_executable(no_guard):
    # 위 목록에 없는 오버로드(current_setting(text, bool) 등)와 설치된 dblink까지 확인한다
    rows = execute(
        "SELECT p.oid::regprocedure::text FROM pg_proc p"
        " WHERE p.proname ~ '^(set_config|current_setting|pg_sleep|query_to_xml|table_to_xml"
        "|database_to_xml|lo_|pg_read_|pg_ls_|pg_stat_file|dblink)'"
        " AND has_function_privilege(p.oid, 'EXECUTE')",
        USER,
    )
    assert rows.rows == []


def test_refuses_superuser(monkeypatch, no_guard):
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
