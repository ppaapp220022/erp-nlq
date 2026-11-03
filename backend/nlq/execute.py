from __future__ import annotations

from nlq.models import Rows, User


def execute(sql: str, user: User) -> Rows:
    """권한을 강제하고 실행한다. DB로 가는 유일한 경로다.

    순서 (docs/architecture.md "guard"):
      1. guard: 단일 SELECT, 테이블·함수 허용 목록, 행 범위(담당자 AND 회사) 재작성, LIMIT (M3)
      2. nlq_readonly 연결, 읽기 전용 트랜잭션, statement_timeout, 행 수 제한 (M2)
    """
    raise NotImplementedError("M2")
