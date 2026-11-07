from __future__ import annotations

from functools import cache
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from nlq.models import Clarification, Failed, GeneratedSQL, GenerationError, User
from nlq.prompt import clarify_enabled, system_prompt, user_message
from nlq.retrieve import retrieve
from nlq.settings import setting

DEFAULT_MODEL = "claude-haiku-5-5"  # 개발용. 결과 표용 측정은 EVAL_MODEL=claude-opus-5-5
EFFORT = "medium"
MAX_TOKENS = 16_000


class _Answer(BaseModel):
    """SQL만 받는 출력. 되묻기를 끈 때, 기준을 확인받은 뒤, 자기 수정으로 다시 만들 때 쓴다(두 번 묻지 않는다)."""

    sql: str = Field(description="PostgreSQL SELECT 문 하나")


class _AnswerOrClarify(BaseModel):
    kind: Literal["sql", "clarify"] = Field(description="SQL을 쓰면 sql, 업무 기준을 되물으면 clarify")
    sql: str = Field(description="kind=sql일 때 PostgreSQL SELECT 문 하나. clarify면 빈 문자열")
    clarification: str = Field(description="kind=clarify일 때 되묻는 한 문장. sql이면 빈 문자열")
    options: list[str] = Field(description="kind=clarify일 때 고를 기준 2~4개. sql이면 빈 목록")


MIN_OPTIONS, MAX_OPTIONS = 2, 4


@cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=setting("ANTHROPIC_API_KEY"))


def generate(question: str, user: User, failed: Failed | None = None, clarified: str | None = None) -> GeneratedSQL:
    """질문을 SQL로 바꾼다 (M2). failed가 있으면 그 SQL과 오류를 보고 고쳐 쓴다 (자기 수정, M5).

    업무 기준이 갈리는 질문이면 SQL 대신 Clarification을 돌려준다(되묻기, M5). clarified는 질문한 사람이
    고른 기준이고, 이것이나 failed가 있으면 SQL만 받는다.

    LLM(Claude API)을 부른다. 결과는 신뢰하지 않는다. 권한 밖 SQL을 만들어도
    execute()가 막아야 하고, 여기서 막았다고 안전하다고 보지 않는다.
    "이번 달" 같은 표현은 eval/config.yaml의 today 기준으로 풀게 한다.
    """
    model = setting("EVAL_MODEL", DEFAULT_MODEL)
    examples = retrieve(question, user)  # NLQ_RETRIEVE가 none이면 빈 목록 (기본 keyword)
    may_clarify = clarify_enabled() and failed is None and clarified is None
    response = _client().messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        output_config={"effort": EFFORT},
        # 지침·열 목록·OKF 묶음은 같은 역할이면 질문마다 같아서 캐시한다. 질문은 사용자 메시지라 캐시 뒤에 붙는다.
        system=[{"type": "text", "text": system_prompt(user=user), "cache_control": {"type": "ephemeral"}}],
        # 예시는 질문마다 달라 캐시 뒤인 사용자 메시지에 넣는다
        messages=[{"role": "user", "content": user_message(question, user, failed, examples, clarified)}],
        output_format=_AnswerOrClarify if may_clarify else _Answer,
    )
    answer = response.parsed_output
    if response.stop_reason != "end_turn" or answer is None:
        raise GenerationError(f"SQL을 만들지 못했다 (stop_reason={response.stop_reason})")
    if getattr(answer, "kind", "sql") == "clarify":
        options = tuple(o.strip() for o in answer.options if o.strip())
        if not answer.clarification.strip() or not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            raise GenerationError("되묻는 질문이나 선택지가 형식에 맞지 않는다")
        return GeneratedSQL(sql="", model=model, clarification=Clarification(answer.clarification.strip(), options))
    if not answer.sql.strip():
        raise GenerationError("SQL이 비어 있다")
    return GeneratedSQL(sql=answer.sql.strip(), model=model)
