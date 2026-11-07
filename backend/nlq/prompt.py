"""generate()에 넘기는 프롬프트를 만든다.

시스템 프롬프트는 질문과 상관없이 같은 바이트여야 캐시된다(접두어 일치). 그래서 지침, 열 목록,
OKF 묶음만 넣고, 질문·사용자·검색한 예시(nlq/retrieve.py)는 사용자 메시지에 둔다. 평가 문항(eval/questions/)은 읽지 않는다.

열 목록과 OKF 묶음은 사용자가 읽을 수 있는 테이블로 거른다(M5). 역할마다 프롬프트가 달라 캐시도 역할마다 따로다.
거르는 것은 정보 노출을 줄이는 장치이고 권한을 지키는 장치가 아니다. 권한은 execute()가 강제한다.

변형은 둘이다. NLQ_PROMPT로 고른다.
  okf     지침 + 열 목록 + OKF 묶음 (기본)
  schema  지침 + 열 목록. 비교 기준 1(프롬프트만 쓴 버전). OKF 묶음과 그것을 가리키는 지침 한 줄만 뺀다

되묻기(M5)는 NLQ_CLARIFY(on 기본, off)로 켜고 끈다. 켜면 언제 되묻는지 지침에 더한다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

import yaml

from nlq.identity import can_read
from nlq.models import Failed, User
from nlq.retrieve import Example
from nlq.settings import ROOT, eval_today, setting

KNOWLEDGE = ROOT / "knowledge"
SCHEMA = ROOT / "db" / "schema.txt"
VARIANTS = ("okf", "schema")
DEFAULT_VARIANT = "okf"
CLARIFY_SETTINGS = ("on", "off")

INSTRUCTIONS = """\
당신은 Odoo 19 ERP 데이터베이스(PostgreSQL 16)에 대한 한국어 질문을 SQL로 바꾼다.

규칙:
- SELECT 문 하나만 쓴다(WITH 가능). 세미콜론으로 여러 문장을 잇지 않는다.
- 아래 <schema>에 있는 테이블과 열만 쓴다. 없는 열을 지어내지 않는다.
- 오늘은 {today}이다. CURRENT_DATE, now() 대신 DATE '{today}'를 쓴다. "이번 달", "지난주" 같은 표현도 이 날짜를 기준으로 푼다.
{knowledge_rule}- 사람이 읽을 이름을 함께 보여 준다(거래처·품목·회사 이름). product_template.name은 jsonb라 name->>'en_US'로 꺼낸다.
- 열 별칭은 짧은 영어 snake_case로 쓴다.
- 질문에 개수 제한이 없으면 LIMIT을 붙이지 않는다. 실행 단계가 행 수를 제한한다.
- 사용자 권한(담당자·회사)으로 거르는 조건은 직접 넣지 않는다. 실행 단계가 강제한다. 단, 질문이 "내 주문"처럼 질문한 사람을 가리키면 아래에 주어진 사용자 id를 쓴다.
{clarify_rule}"""
KNOWLEDGE_RULE = """\
- <knowledge>의 지표 정의와 주의 사항을 따른다. 특히 송장은 move_type과 state를 함께 걸고, 여러 문서를 합칠 때는 부호 있는 금액 열을 쓴다.
"""


CLARIFY_RULE = """\
- 아래 업무 기준 중 하나에서 답이 갈리는데 질문에도 지표 정의에도 단서가 없으면, SQL 대신 되묻는다(kind=clarify). 되물음은 한 문장, 선택지는 2~4개의 짧은 기준이다.
  1. 주문 기준과 송장 기준: "판매액", "판매 금액", "판매 실적", "실적"처럼 어느 쪽인지 정하지 않은 금액. "매출"은 송장 기준, "주문 금액"·"수주"는 주문 기준으로 정해져 있으니 묻지 않는다.
  2. 부가세: 주문·발주·송장 금액을 묻는데 부가세 포함·제외가 없고 지표 정의로도 정해지지 않을 때. 매출은 제외, 미수금·남은 금액은 포함으로 정해져 있다.
  3. 환불: 송장 금액 합계에서 환불을 뺄지 정해지지 않을 때. 매출과 미수금은 정의대로 뺀다.
- 위 셋이 아니면 되묻지 않는다. 목록·건수·재고·날짜 범위처럼 기준이 하나뿐인 질문은 바로 SQL을 쓴다.
"""


def clarify_enabled() -> bool:
    value = setting("NLQ_CLARIFY", "on")
    if value not in CLARIFY_SETTINGS:
        raise RuntimeError(f"NLQ_CLARIFY는 {', '.join(CLARIFY_SETTINGS)} 중 하나다: {value}")
    return value == "on"


def prompt_variant() -> str:
    variant = setting("NLQ_PROMPT", DEFAULT_VARIANT)
    if variant not in VARIANTS:
        raise RuntimeError(f"NLQ_PROMPT는 {', '.join(VARIANTS)} 중 하나다: {variant}")
    return variant


def doc_tables(path: Path) -> list[str] | None:
    """OKF 문서 앞머리의 tables (docs/architecture.md "지식 층"). 앞머리나 tables가 없으면 None."""
    match = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S)
    meta = yaml.safe_load(match.group(1)) if match else None
    tables = meta.get("tables") if isinstance(meta, dict) else None
    return list(tables) if isinstance(tables, list) and tables else None


def _readable(tables: list[str] | None, user: User | None) -> bool:
    # tables를 모르는 문서는 역할이 있는 사용자에게 넣지 않는다(실패 시 닫힘)
    if user is None:
        return True
    return tables is not None and all(can_read(t, user) for t in tables)


def _schema(user: User | None) -> str:
    # schema.txt는 한 줄에 테이블 하나: "테이블(열 형, ...)"
    lines = SCHEMA.read_text().strip().splitlines()
    return "\n".join(line for line in lines if _readable([line.split("(", 1)[0]], user))


def _knowledge(user: User | None) -> str:
    docs = sorted(p for p in KNOWLEDGE.rglob("*.md") if p.name != "README.md")
    return "\n\n".join(
        f'<doc path="{p.relative_to(KNOWLEDGE)}">\n{p.read_text().strip()}\n</doc>'
        for p in docs
        if _readable(doc_tables(p), user)
    )


def system_prompt(variant: str | None = None, user: User | None = None) -> str:
    """user가 없으면 거르지 않은 전체 프롬프트다(테스트·비교용). generate()는 항상 user를 넘긴다."""
    okf = (variant or prompt_variant()) == "okf"
    prompt = INSTRUCTIONS.format(
        today=eval_today(),
        knowledge_rule=KNOWLEDGE_RULE if okf else "",
        clarify_rule=CLARIFY_RULE if clarify_enabled() else "",
    )
    prompt += f"\n<schema>\n{_schema(user)}\n</schema>\n"
    if okf:
        prompt += f"\n<knowledge>\n{_knowledge(user)}\n</knowledge>\n"
    return prompt


def user_message(
    question: str,
    user: User,
    failed: Failed | None = None,
    examples: Sequence[Example] = (),
    clarified: str | None = None,
) -> str:
    message = f"질문한 사용자: res_users.id = {user.odoo_uid}\n\n"
    if examples:
        shots = "\n".join(
            f"<example>\n<question>{e.question}</question>\n<sql>\n{e.sql}\n</sql>\n</example>" for e in examples
        )
        message += (
            "비슷한 질문의 예시다. 질문한 사용자와 다른 사용자 기준으로 쓴 것도 있다. "
            f"그대로 베끼지 말고 이 질문에 맞게 쓴다.\n<examples>\n{shots}\n</examples>\n\n"
        )
    message += f"질문: {question}"
    if clarified is not None:
        message += f"\n\n질문한 사람이 확인한 기준: {clarified}\n이 기준으로 SQL을 쓴다. 다시 묻지 않는다."
    if failed is not None:
        message += (
            f"\n\n앞서 만든 SQL이 실행되지 않았다. 오류를 보고 고친 SQL 하나를 다시 쓴다."
            f"\n<previous_sql>\n{failed.sql}\n</previous_sql>\n<error>\n{failed.error}\n</error>"
        )
    return message
