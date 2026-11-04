from __future__ import annotations

import psycopg

from nlq.models import ExecutionError, Rows, User
from nlq.settings import readonly_conninfo

STATEMENT_TIMEOUT_MS = 10_000
MAX_ROWS = 1_000
CONNECT_TIMEOUT_S = 5

NO_ROW_SCOPE = "행 범위(담당자·회사)가 아직 걸리지 않았다. guard는 M3에서 붙는다."


def execute(sql: str, user: User) -> Rows:
    """권한을 강제하고 실행한다. DB로 가는 유일한 경로다.

    순서 (docs/architecture.md "guard"):
      1. guard: 단일 SELECT, 테이블·함수 허용 목록, 행 범위(담당자 AND 회사) 재작성, LIMIT (M3)
      2. nlq_readonly 연결, 읽기 전용 트랜잭션, statement_timeout, 행 수 제한 (M2)
    """
    with _connect() as conn:
        try:
            return _run(conn, sql)
        finally:
            # 사용자 SQL이 트랜잭션 안의 설정(set_config)을 바꿨을 수 있다. 결과와 상관없이 버린다.
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
    conn.execute("SELECT set_config('statement_timeout', %s, true)", (str(STATEMENT_TIMEOUT_MS),))
    # 서버 커서(DECLARE CURSOR)로 실행한다. DB가 SELECT 하나만 받고(쓰기 CTE·SET·여러 문장 거부),
    # 결과는 필요한 만큼만 가져온다. FETCH는 한 번만 한다. 시간 제한은 문장마다 걸리고, 사용자 SQL이
    # set_config로 바꾼 값은 다음 문장부터 적용되기 때문이다.
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
        warnings=[NO_ROW_SCOPE],
    )


def _message(e: psycopg.Error) -> str:
    # DB 오류의 첫 줄만 넘긴다. 자기 수정(M5)이 이 메시지를 LLM에 다시 넣는다.
    if isinstance(e, psycopg.errors.QueryCanceled):
        return f"시간 제한 {STATEMENT_TIMEOUT_MS // 1000}초를 넘겨 취소됐다"
    return str(e).splitlines()[0] if str(e) else type(e).__name__
