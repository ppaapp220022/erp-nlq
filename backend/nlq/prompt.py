"""generate()에 넘기는 프롬프트를 만든다.

시스템 프롬프트는 질문과 상관없이 같은 바이트여야 캐시된다(접두어 일치). 그래서 지침, 열 목록,
OKF 묶음만 넣고, 질문과 사용자는 사용자 메시지에 둔다. 평가 문항(eval/questions/)은 읽지 않는다.
"""

from __future__ import annotations

from nlq.models import User
from nlq.settings import ROOT, eval_today

KNOWLEDGE = ROOT / "knowledge"
SCHEMA = ROOT / "db" / "schema.txt"

INSTRUCTIONS = """\
당신은 Odoo 19 ERP 데이터베이스(PostgreSQL 16)에 대한 한국어 질문을 SQL로 바꾼다.

규칙:
- SELECT 문 하나만 쓴다(WITH 가능). 세미콜론으로 여러 문장을 잇지 않는다.
- 아래 <schema>에 있는 테이블과 열만 쓴다. 없는 열을 지어내지 않는다.
- 오늘은 {today}이다. CURRENT_DATE, now() 대신 DATE '{today}'를 쓴다. "이번 달", "지난주" 같은 표현도 이 날짜를 기준으로 푼다.
- <knowledge>의 지표 정의와 주의 사항을 따른다. 특히 송장은 move_type과 state를 함께 걸고, 여러 문서를 합칠 때는 부호 있는 금액 열을 쓴다.
- 사람이 읽을 이름을 함께 보여 준다(거래처·품목·회사 이름). product_template.name은 jsonb라 name->>'en_US'로 꺼낸다.
- 열 별칭은 짧은 영어 snake_case로 쓴다.
- 질문에 개수 제한이 없으면 LIMIT을 붙이지 않는다. 실행 단계가 행 수를 제한한다.
- 사용자 권한(담당자·회사)으로 거르는 조건은 직접 넣지 않는다. 실행 단계가 강제한다. 단, 질문이 "내 주문"처럼 질문한 사람을 가리키면 아래에 주어진 사용자 id를 쓴다.
"""


def _knowledge() -> str:
    docs = sorted(p for p in KNOWLEDGE.rglob("*.md") if p.name != "README.md")
    return "\n\n".join(f'<doc path="{p.relative_to(KNOWLEDGE)}">\n{p.read_text().strip()}\n</doc>' for p in docs)


def system_prompt() -> str:
    return (
        INSTRUCTIONS.format(today=eval_today())
        + f"\n<schema>\n{SCHEMA.read_text().strip()}\n</schema>\n"
        + f"\n<knowledge>\n{_knowledge()}\n</knowledge>\n"
    )


def user_message(question: str, user: User) -> str:
    return f"질문한 사용자: res_users.id = {user.odoo_uid}\n\n질문: {question}"
