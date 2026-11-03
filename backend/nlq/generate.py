from __future__ import annotations

from nlq.models import GeneratedSQL, User


def generate(question: str, user: User) -> GeneratedSQL:
    """질문을 SQL로 바꾼다 (M2).

    LLM(Claude API)을 부른다. 결과는 신뢰하지 않는다. 권한 밖 SQL을 만들어도
    execute()가 막아야 하고, 여기서 막았다고 안전하다고 보지 않는다.
    "이번 달" 같은 표현은 eval/config.yaml의 today 기준으로 풀게 한다.
    """
    raise NotImplementedError("M2")
