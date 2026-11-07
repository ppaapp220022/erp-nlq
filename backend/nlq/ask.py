"""질문 → SQL → 실행, 실패하면 오류를 넣어 한 번 다시 만든다 (자기 수정, M5).

generate()와 execute()를 차례로 부를 뿐이다. 다시 만든 SQL도 execute()가 처음부터 검증하므로
재시도가 권한 범위를 넓히지 않는다. CLI와 평가가 쓴다. 화면은 같은 순서를 API 두 개로 밟는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from nlq.execute import execute
from nlq.generate import generate
from nlq.models import ExecutionError, Failed, Rows, User

RETRIES = 1  # plan.md: SQL 실패 시 에러를 넣어 1회 재시도


@dataclass(frozen=True)
class Attempt:
    sql: str
    model: str
    rows: Rows | None = None
    error: ExecutionError | None = None


def ask(question: str, user: User, retries: int = RETRIES) -> list[Attempt]:
    """시도마다 하나씩 돌려준다. 마지막 것이 결과다. 생성 실패(GenerationError)는 그대로 올린다."""
    attempts: list[Attempt] = []
    failed: Failed | None = None
    for _ in range(retries + 1):
        generated = generate(question, user, failed)
        try:
            rows = execute(generated.sql, user)
        except ExecutionError as e:
            attempts.append(Attempt(sql=generated.sql, model=generated.model, error=e))
            failed = Failed(sql=generated.sql, error=str(e))
            continue
        attempts.append(Attempt(sql=generated.sql, model=generated.model, rows=rows))
        break
    return attempts
