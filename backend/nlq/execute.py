from __future__ import annotations

import psycopg
from psycopg import sql as pgsql

from nlq.guard import guard
from nlq.models import ExecutionError, Rows, User
from nlq.settings import readonly_conninfo

STATEMENT_TIMEOUT_MS = 10_000
MAX_ROWS = 1_000
CONNECT_TIMEOUT_S = 5


def execute(sql: str, user: User) -> Rows:
    """권한을 강제하고 실행한다. DB로 가는 유일한 경로다.

    순서 (docs/architecture.md "guard"):
      1. guard: 단일 SELECT, 테이블·함수 허용 목록, 행 범위(담당자 AND 회사) 재작성, LIMIT (M3)
      2. nlq_readonly 연결, 읽기 전용 트랜잭션, statement_timeout, 행 수 제한 (M2)
    guard가 거부하면 GuardError(ExecutionError)를 내고 DB에 접속하지 않는다.
    """
    sql = guard(sql, user, max_rows=MAX_ROWS)
    with _connect() as conn:
        try:
            return _run(conn, sql)
        finally:
            # SET LOCAL로 건 설정을 버린다. 사용자 SQL은 set_config 실행 권한이 없지만(db/readonly_role.sql),
            # 결과와 상관없이 트랜잭션을 남기지 않는다.
            conn.rollback()


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(**readonly_conninfo(), connect_timeout=CONNECT_TIMEOUT_S, application_name="nlq")
    conn.read_only = True  # BEGIN READ ONLY. 역할의 default_transaction_read_only와 별개로 한 번 더 건다
    superuser, bypass_rls = conn.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    if superuser or bypass_rls:
        conn.close()
        raise RuntimeError("질의 계층은 superuser나 BYPASSRLS 역할로 접속하지 않는다 (절대 규칙 2)")
    return conn


def _run(conn: psycopg.Connection, sql: str) -> Rows:
    # set_config는 nlq_readonly에서 실행 권한을 회수했으므로 SET LOCAL로 건다. SET은 값 자리에
    # 바인드 변수를 받지 않아 리터럴로 넣는다.
    conn.execute(pgsql.SQL("SET LOCAL statement_timeout = {}").format(pgsql.Literal(int(STATEMENT_TIMEOUT_MS))))
    # 서버 커서(DECLARE CURSOR)로 실행한다. DB가 SELECT 하나만 받고(쓰기 CTE·SET·여러 문장 거부),
    # 결과는 필요한 만큼만 가져온다. FETCH는 한 번만 한다. 시간 제한은 문장마다 걸리므로, 사용자 SQL이
    # 설정을 바꿀 길이 생겨도 바뀐 값은 다음 문장부터 적용되기 때문이다.
    with conn.cursor(name="nlq") as cur:
        try:
            cur.execute(sql)
            fetched = cur.fetchmany(MAX_ROWS + 1)
        except psycopg.Error as e:
            raise ExecutionError(_message(e)) from e
        columns = [d.name for d in cur.description or []]
    return Rows(
        columns=columns,
        rows=[tuple(r) for r in fetched[:MAX_ROWS]],
        executed_sql=sql,
        truncated=len(fetched) > MAX_ROWS,
    )


def _message(e: psycopg.Error) -> str:
    # DB 오류의 첫 줄만 넘긴다. 자기 수정(M5)이 이 메시지를 LLM에 다시 넣는다.
    if isinstance(e, psycopg.errors.QueryCanceled):
        return f"시간 제한 {STATEMENT_TIMEOUT_MS // 1000}초를 넘겨 취소됐다"
    return str(e).splitlines()[0] if str(e) else type(e).__name__
