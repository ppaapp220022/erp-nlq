"""RLS 경로 테스트 (M6 비교, ADR 0005). 우회 테스트는 test_guard.py가 방식마다 돌린다(conftest.py `enforce`).

여기서는 RLS 경로에만 있는 것을 본다: 정책 파일이 규칙과 같은지, 문맥 없이 실행하면 닫히는지,
사용자 SQL이 문맥을 바꾸지 못하는지. DB 테스트는 nlq_rls로 접속할 DB가 있어야 돈다.
"""

import psycopg
import pytest

from nlq import ExecutionError, execute
from nlq.identity import TABLES
from nlq.rls import policies_sql
from nlq.settings import ROOT, readonly_conninfo
from nlq.users import load_users

USERS = {login: p.user for login, p in load_users().items()}
KIM = USERS["sales.kim"]


def _rls_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(rls=True), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _rls_available(), reason="nlq_rls로 접속할 DB가 없다")


def test_policy_file_matches_rules():
    # identity.py를 바꾸고 정책 파일을 다시 만들지 않으면 두 경로의 규칙이 갈라진다
    assert (ROOT / "db" / "rls_policies.sql").read_text() == policies_sql()


@pytest.fixture
def rls_conn():
    conn = psycopg.connect(**readonly_conninfo(rls=True), connect_timeout=2)
    conn.read_only = True
    yield conn
    conn.close()


@db
@pytest.mark.parametrize("table", sorted(TABLES))
def test_no_context_fails_closed(rls_conn, table):
    # execute()를 거치지 않아 문맥이 없으면 행 대신 오류가 나온다. 전역 규칙이 TRUE인 res_company도 같다
    with pytest.raises(psycopg.errors.RaiseException, match="권한 문맥"):
        rls_conn.execute(f"SELECT count(id) FROM {table}").fetchone()


@db
def test_context_is_transaction_local(rls_conn):
    # SET LOCAL 값은 트랜잭션이 끝나면 비워진다. 같은 연결의 다음 트랜잭션은 다시 닫힌다
    rls_conn.execute("SET LOCAL nlq.uid = '7'")
    rls_conn.rollback()
    with pytest.raises(psycopg.errors.RaiseException):
        rls_conn.execute("SELECT count(*) FROM res_company").fetchone()


@db
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT set_config('nlq.uid', '2', true)",
        "SELECT current_setting('nlq.groups')",
        "SELECT nlq._context('nlq.uid')",
        "SELECT pg_catalog.set_config('nlq.groups', 'sales_team.group_sale_salesman_all_leads', true), count(*) FROM sale_order",
    ],
)
@pytest.mark.usefixtures("rls_no_guard")
def test_user_sql_cannot_touch_context(sql):
    # guard 없이 RLS만 남겨도 사용자 SQL은 문맥을 읽거나 바꾸는 함수를 실행할 수 없다
    with pytest.raises(ExecutionError, match="permission denied"):
        execute(sql, KIM)


@db
@pytest.mark.usefixtures("rls_no_guard")
def test_context_functions_return_only_own_values():
    # 정책용 함수는 nlq_rls에 열려 있다. 불러도 자기 문맥만 나온다
    rows = execute("SELECT nlq.uid(), nlq.has_group('sales_team.group_sale_salesman_all_leads')", KIM).rows
    assert rows == [(7, False)]


@db
def test_guard_still_rejects_in_rls_mode(monkeypatch):
    # rls 방식에서도 guard 검증(문장·함수·테이블 허용 목록)은 그대로다
    monkeypatch.setenv("NLQ_ENFORCE", "rls")
    with pytest.raises(ExecutionError):
        execute("SELECT nlq.uid()", KIM)
    with pytest.raises(ExecutionError):
        execute("SELECT * FROM purchase_order", KIM)


@db
def test_rls_mode_runs_sql_unrewritten(monkeypatch):
    monkeypatch.setenv("NLQ_ENFORCE", "rls")
    rows = execute("SELECT count(*) FROM sale_order", KIM)
    assert rows.rows == [(8,)]
    assert "user_id" not in rows.executed_sql
