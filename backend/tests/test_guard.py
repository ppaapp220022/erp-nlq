"""guard 우회 테스트 (M3). 권한 계층을 바꾸면 여기에 하나 이상 더한다 (CLAUDE.md 절대 규칙 5).

앞부분은 DB 없이 돈다. guard가 막아야 하는 SQL을 막는지 본다.
뒷부분은 로컬 DB(nlq_readonly)가 있어야 돈다. 막지 않는 SQL이 권한 밖 행을 돌려주지 않는지 본다.
Odoo가 보여 주는 행 수와의 비교는 test_odoo_scope.py에 있다.
"""

import psycopg
import pytest
import sqlglot
from sqlglot import exp

from nlq import ExecutionError, execute
from nlq.guard import GuardError, guard
from nlq.identity import TABLES, row_scope
from nlq.settings import readonly_conninfo
from nlq.users import load_users

USERS = {login: p.user for login, p in load_users().items()}
KIM = USERS["sales.kim"]  # 영업 사원. 판매 주문은 본인(7) + 담당자 없음
CHOI = USERS["stock.choi"]  # 재고 담당. 고객 송장을 못 본다
ADMIN = USERS["admin"]


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


def scalar(sql, user):
    return execute(sql, user).rows[0][0]


# --- 막아야 하는 SQL (DB 없이) ---

REJECT = {
    # 문장 하나, SELECT만
    "여러 문장": "SELECT 1; SELECT 2",
    "주석 뒤 두 번째 문장": "SELECT 1 /* x */; DELETE FROM sale_order",
    "UPDATE": "UPDATE sale_order SET user_id = 7",
    "SET": "SET statement_timeout = 0",
    "쓰기 CTE": "WITH d AS (DELETE FROM sale_order RETURNING id) SELECT * FROM d",
    "SELECT INTO": "SELECT * INTO t FROM sale_order",
    "FOR UPDATE": "SELECT * FROM sale_order FOR UPDATE",
    "파싱 실패": "SELECT FROM WHERE",
    "빈 문자열": "",
    # 위험 함수 (architecture.md guard 3번)
    "set_config": "SELECT set_config('statement_timeout', '0', false)",
    "스키마 붙인 set_config": "SELECT pg_catalog.set_config('statement_timeout', '0', false)",
    "따옴표 함수 이름": 'SELECT "pg_sleep"(20)',
    "pg_sleep": "SELECT pg_sleep(20)",
    "current_setting": "SELECT current_setting('is_superuser')",
    "query_to_xml": "SELECT query_to_xml('select * from purchase_order', true, true, '')",
    "pg_read_file": "SELECT pg_read_file('/etc/passwd')",
    "dblink": "SELECT * FROM dblink('dbname=erp', 'select 1') AS t(x int)",
    # DB에서 실행 권한을 회수하지 않아 guard만 막는 함수 (db/readonly_role.sql 끝)
    "pg_advisory_lock": "SELECT pg_advisory_lock(1)",
    "pg_notify": "SELECT pg_notify('c', 'x')",
    "pg_cancel_backend": "SELECT pg_cancel_backend(1)",
    "FROM 안 함수": "SELECT * FROM generate_series(1, 10)",
    "regclass 형 변환": "SELECT 'pg_authid'::regclass",
    "자리표시자": "SELECT * FROM sale_order WHERE id = $1",
    # 허용 목록 밖 테이블
    "시스템 카탈로그": "SELECT rolname FROM pg_roles",
    "스키마 붙인 카탈로그": "SELECT * FROM pg_catalog.pg_settings",
    "information_schema": "SELECT * FROM information_schema.tables",
    "허용 안 된 Odoo 테이블": "SELECT * FROM res_users_log",
    "다른 스키마의 같은 이름": "SELECT * FROM pg_temp.sale_order",
    "따옴표 대문자 이름": 'SELECT * FROM "SALE_ORDER"',
    "ASCII가 아닌 대문자": "SELECT * FROM STOC\u212a_QUANT",  # 켈빈 기호. str.lower()로는 stock_quant가 된다
    "깊은 중첩": "SELECT " + "(" * 5000 + "1" + ")" * 5000,
    # CTE 이름으로 실제 테이블 숨기기
    "뒤에 정의된 CTE 이름": "WITH a AS (SELECT * FROM pg_roles), pg_roles AS (SELECT 1) SELECT * FROM a",
    "서브쿼리 안 CTE 이름": "SELECT * FROM (WITH pg_roles AS (SELECT 1) SELECT * FROM pg_roles) s, pg_roles",
    "재귀 아닌 CTE의 자기 참조": "WITH pg_roles AS (SELECT * FROM pg_roles) SELECT * FROM pg_roles",
    # 테이블 없이 읽는 길
    "TABLE 문": "TABLE sale_order",
    "VALUES": "SELECT * FROM (VALUES (1)) v",
    "ROWS FROM": "SELECT * FROM ROWS FROM (generate_series(1, 2))",
    "current_user": "SELECT current_user",
    "version": "SELECT version()",
    "row_to_json": "SELECT row_to_json(s) FROM sale_order s",
}


@pytest.mark.parametrize("sql", REJECT.values(), ids=REJECT.keys())
def test_rejects(sql):
    with pytest.raises(GuardError):
        guard(sql, ADMIN)


@pytest.mark.parametrize(
    ("user", "sql"),
    [
        (KIM, "SELECT * FROM purchase_order"),  # 영업 사원은 구매를 못 본다 (Odoo ACL)
        (KIM, "SELECT p.id FROM sale_order s JOIN purchase_order_line p ON p.id = s.id"),
        (KIM, "SELECT (SELECT count(*) FROM purchase_order)"),
        (CHOI, "SELECT * FROM account_move"),  # 재고 담당은 송장을 못 본다
        (CHOI, "WITH m AS (SELECT * FROM account_move) SELECT count(*) FROM m"),
    ],
)
def test_rejects_tables_outside_role(user, sql):
    with pytest.raises(GuardError):
        guard(sql, user)


def test_guard_error_is_execution_error():
    # 호출하는 쪽(CLI, 자기 수정)은 ExecutionError 하나로 받는다
    assert issubclass(GuardError, ExecutionError)


def test_comments_are_dropped():
    assert "secret" not in guard("SELECT 1 /* secret */ -- secret", ADMIN)


def test_limit_is_forced():
    sql = guard("SELECT id FROM sale_order", ADMIN, max_rows=5)
    assert "LIMIT 6" in sql
    assert "LIMIT 3" in guard("SELECT id FROM sale_order LIMIT 3", ADMIN, max_rows=5)
    assert "LIMIT 6" in guard("SELECT id FROM sale_order LIMIT 100000", ADMIN, max_rows=5)
    assert "LIMIT 6" in guard("SELECT id FROM sale_order LIMIT ALL", ADMIN, max_rows=5)
    assert guard("SELECT id FROM sale_order UNION SELECT id FROM sale_order", ADMIN, max_rows=5).endswith("LIMIT 6")


# --- 막지 않는 SQL이 권한 밖 행을 내지 않는지 (DB) ---

KIM_ORDERS = "(user_id = 7 OR user_id IS NULL)"  # Odoo sale_order_personal_rule


@db
def test_salesman_sees_own_and_unassigned_orders():
    assert scalar("SELECT count(*) FROM sale_order", KIM) == 8
    assert scalar("SELECT count(*) FROM sale_order WHERE 1 = 1 OR user_id = 8", KIM) == 8
    assert scalar(f"SELECT count(*) FROM sale_order WHERE NOT {KIM_ORDERS}", KIM) == 0


@db
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM sale_order WHERE user_id = 8 OR (user_id = 8 AND 1 = 1)",  # OR로 조건 풀기
        "SELECT count(*) FROM sale_order WHERE user_id <> 7",
        "SELECT count(*) FROM public.sale_order WHERE user_id = 8",  # 스키마 붙이기
        "SELECT count(*) FROM SALE_ORDER WHERE user_id = 8",  # 대문자
        "SELECT count(*) FROM ONLY sale_order WHERE user_id = 8",
        "SELECT count(*) FROM sale_order AS purchase_order WHERE user_id = 8",  # 별칭 바꾸기
        "SELECT count(*) FROM (SELECT * FROM sale_order) s WHERE user_id = 8",  # 서브쿼리
        "WITH x AS (SELECT * FROM sale_order) SELECT count(*) FROM x WHERE user_id = 8",  # CTE
        "WITH sale_order AS (SELECT * FROM sale_order) SELECT count(*) FROM sale_order WHERE user_id = 8",
        "SELECT (SELECT count(*) FROM sale_order WHERE user_id = 8)",  # SELECT 목록 안
        "SELECT count(*) FROM res_partner p WHERE EXISTS (SELECT 1 FROM sale_order o WHERE o.partner_id = p.id AND o.user_id = 8)",
        "SELECT count(*) FROM (SELECT id FROM sale_order WHERE user_id = 8 UNION ALL SELECT id FROM sale_order WHERE user_id = 9) u",
        "SELECT count(*) FROM sale_order a JOIN sale_order b ON a.id = b.id WHERE b.user_id = 8",
        "SELECT count(*) FROM res_partner p LEFT JOIN sale_order o ON o.partner_id = p.id AND o.user_id = 8 WHERE o.id IS NOT NULL",
        "SELECT count(*) FROM sale_order_line WHERE salesman_id = 8",  # 주문 라인도 같은 범위
        "SELECT count(*) FROM stock_picking k JOIN sale_order o ON o.id = k.sale_id WHERE o.user_id = 8",
        "WITH RECURSIVE r AS (SELECT * FROM sale_order) SELECT count(*) FROM r WHERE user_id = 8",
        "WITH x AS MATERIALIZED (SELECT * FROM sale_order) SELECT count(*) FROM x WHERE user_id = 8",
        "SELECT count(*) FROM (SELECT 1) t, LATERAL (SELECT * FROM sale_order WHERE user_id = 8) s",
        "SELECT count(*) FROM sale_order WHERE id = ANY(ARRAY(SELECT id FROM sale_order WHERE user_id = 8))",
        'SELECT count(*) FROM public."sale_order" WHERE user_id = 8',
        "SELECT count(*) FROM sale_order JOIN sale_order_line USING (id) WHERE sale_order.user_id = 8",
    ],
)
def test_salesman_cannot_reach_other_orders(sql):
    assert scalar(sql, KIM) == 0


@db
def test_salesman_sees_only_own_customer_invoices():
    assert scalar("SELECT count(*) FROM account_move", KIM) == 13
    assert scalar("SELECT count(*) FROM account_move WHERE move_type NOT IN ('out_invoice', 'out_refund')", KIM) == 0
    assert scalar("SELECT count(*) FROM account_move WHERE invoice_user_id <> 7", KIM) == 0


@db
def test_stock_user_sees_all_orders_in_company():
    # 재고 담당에게는 sale_order 그룹 규칙이 없어 회사 규칙만 걸린다 (ADR 0002)
    assert scalar("SELECT count(*) FROM sale_order", CHOI) == 24


@db
def test_timeout_cannot_be_turned_off():
    with pytest.raises(GuardError):
        execute("SELECT set_config('statement_timeout', '0', true), pg_sleep(20)", KIM)


@db
def test_executed_sql_is_the_rewritten_one():
    rows = execute("SELECT count(*) FROM sale_order", KIM)
    assert "user_id" in rows.executed_sql
    assert not rows.warnings


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM sale_order",
        "WITH x AS (SELECT * FROM sale_order) SELECT * FROM x JOIN account_move m ON m.id = x.id",
        "SELECT (SELECT count(*) FROM sale_order_line), p.name FROM res_partner p JOIN res_users u ON u.partner_id = p.id",
        "SELECT * FROM product_product p WHERE EXISTS (SELECT 1 FROM stock_quant q WHERE q.product_id = p.id)",
        "SELECT id FROM sale_order UNION SELECT id FROM account_move",
    ],
)
def test_every_table_in_output_is_scoped(sql):
    # guard가 내는 SQL을 다시 파싱해, 실제 테이블이 모두 행 범위 서브쿼리 안에만 있는지 본다.
    # sqlglot 버전이 바뀌어 재작성이 빠지면 여기서 걸린다.
    out = sqlglot.parse_one(guard(sql, KIM), read="postgres")
    tables = list(out.find_all(exp.Table))
    assert tables
    for table in tables:
        if table.name not in TABLES:
            continue  # CTE 참조
        select = table.find_ancestor(exp.Select)
        if table.find_ancestor(exp.Where) is not None and table.find_ancestor(exp.Where).parent is not select:
            continue  # 행 범위 조건 안의 테이블(res_company, product_template 등)은 guard가 넣은 것이다
        scope = sqlglot.parse_one(row_scope(table.name, KIM), read="postgres")
        assert select.args["where"].this == scope, table.name
