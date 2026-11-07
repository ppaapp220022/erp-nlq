from __future__ import annotations

from functools import cache

import anthropic
from pydantic import BaseModel, Field

from nlq.models import Failed, GeneratedSQL, GenerationError, User
from nlq.prompt import system_prompt, user_message
from nlq.settings import setting

DEFAULT_MODEL = "claude-haiku-5-5"  # 개발용. 결과 표용 측정은 EVAL_MODEL=claude-opus-5-5
EFFORT = "medium"
MAX_TOKENS = 16_000


class _Answer(BaseModel):
    sql: str = Field(description="PostgreSQL SELECT 문 하나")


@cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=setting("ANTHROPIC_API_KEY"))


def generate(question: str, user: User, failed: Failed | None = None) -> GeneratedSQL:
    """질문을 SQL로 바꾼다 (M2). failed가 있으면 그 SQL과 오류를 보고 고쳐 쓴다 (자기 수정, M5).

    LLM(Claude API)을 부른다. 결과는 신뢰하지 않는다. 권한 밖 SQL을 만들어도
    execute()가 막아야 하고, 여기서 막았다고 안전하다고 보지 않는다.
    "이번 달" 같은 표현은 eval/config.yaml의 today 기준으로 풀게 한다.
    """
    model = setting("EVAL_MODEL", DEFAULT_MODEL)
    response = _client().messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        output_config={"effort": EFFORT},
        # 지침·열 목록·OKF 묶음은 질문마다 같아서 캐시한다. 질문은 사용자 메시지라 캐시 뒤에 붙는다.
        system=[{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_message(question, user, failed)}],
        output_format=_Answer,
    )
    if response.stop_reason != "end_turn" or response.parsed_output is None:
        raise GenerationError(f"SQL을 만들지 못했다 (stop_reason={response.stop_reason})")
    return GeneratedSQL(sql=response.parsed_output.sql.strip(), model=model)
