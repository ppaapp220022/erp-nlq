"""generate()와 프롬프트 테스트. Claude API를 부르지 않는다.

실제 호출 확인은 NLQ_LIVE_API=1일 때만 돈다(비용이 들어 CI에서는 돌리지 않는다).
"""

import importlib
import os
import re
from types import SimpleNamespace

import pytest

from nlq import Failed, GenerationError, User, generate
from nlq.prompt import KNOWLEDGE, SCHEMA, VARIANTS, doc_tables, system_prompt, user_message
from nlq.settings import ROOT, eval_today
from nlq.users import load_users

generate_module = importlib.import_module("nlq.generate")

USER = User(odoo_uid=6, login="demo", company_ids=(1,))


def test_system_prompt_is_stable_for_caching():
    # 질문·사용자와 무관하게 같은 바이트여야 캐시된다.
    assert system_prompt() == system_prompt()
    assert "{today}" not in system_prompt()
    assert f"DATE '{eval_today()}'" in system_prompt()


def test_system_prompt_has_schema_and_every_knowledge_doc():
    prompt = system_prompt()
    assert SCHEMA.read_text().strip() in prompt
    for path in KNOWLEDGE.rglob("*.md"):
        tag = f'<doc path="{path.relative_to(KNOWLEDGE)}">'
        assert (tag in prompt) == (path.name != "README.md")


def test_schema_variant_drops_only_knowledge():
    # 비교 기준 1: OKF 묶음과 그것을 가리키는 지침만 빠지고 나머지는 같다.
    okf, schema = system_prompt("okf"), system_prompt("schema")
    assert "<knowledge>" in okf and "<knowledge>" not in schema
    assert SCHEMA.read_text().strip() in schema
    assert f"DATE '{eval_today()}'" in schema
    rule = next(line for line in okf.splitlines() if "<knowledge>의" in line)
    assert okf.split("\n<knowledge>\n")[0].replace(rule + "\n", "") == schema


def test_prompt_variant_from_setting(monkeypatch):
    assert system_prompt() == system_prompt("okf")
    monkeypatch.setenv("NLQ_PROMPT", "schema")
    assert system_prompt() == system_prompt("schema")
    monkeypatch.setenv("NLQ_PROMPT", "nope")
    with pytest.raises(RuntimeError, match="NLQ_PROMPT"):
        system_prompt()


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_eval_question_in_prompt(variant):
    # 절대 규칙 4: 평가 문항은 프롬프트에 들어가지 않는다.
    prompt = system_prompt(variant)
    for q in (ROOT / "eval" / "questions").glob("*.yaml"):
        for question in re.findall(r"^question:\s*(.+)$", q.read_text(), re.M):
            assert question.strip() not in prompt, q.name


def test_user_message_carries_question_and_user():
    message = user_message("내 주문 수", USER)
    assert "내 주문 수" in message
    assert "res_users.id = 6" in message


def test_user_message_carries_failed_attempt():
    # 자기 수정: 앞 SQL과 오류는 사용자 메시지에 붙는다. 시스템 프롬프트(캐시)는 그대로다
    assert "<error>" not in user_message("q", USER)
    message = user_message("q", USER, Failed(sql="SELECT bad", error='column "bad" does not exist'))
    assert "<previous_sql>\nSELECT bad\n</previous_sql>" in message
    assert 'column "bad" does not exist' in message


def _fake_client(monkeypatch, *, stop_reason="end_turn", sql="SELECT 1"):
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        parsed = generate_module._Answer(sql=sql) if stop_reason == "end_turn" else None
        return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed)

    client = SimpleNamespace(messages=SimpleNamespace(parse=parse))
    monkeypatch.setattr(generate_module, "_client", lambda: client)
    return calls


def test_generate_caches_system_prompt_and_uses_configured_model(monkeypatch):
    calls = _fake_client(monkeypatch, sql="  SELECT 1\n")
    monkeypatch.setenv("EVAL_MODEL", "claude-opus-5-5")
    result = generate("고유한-질문-문자열", USER)
    assert result.sql == "SELECT 1"
    assert result.model == "claude-opus-5-5"
    (call,) = calls
    assert call["model"] == "claude-opus-5-5"
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "고유한-질문-문자열" not in call["system"][0]["text"]


def test_generate_sends_failed_attempt_in_user_message(monkeypatch):
    calls = _fake_client(monkeypatch)
    generate("질문", USER, Failed(sql="SELECT bad", error="oops"))
    (call,) = calls
    assert call["system"][0]["text"] == system_prompt(user=USER)
    assert "SELECT bad" in call["messages"][0]["content"] and "oops" in call["messages"][0]["content"]


def test_generate_uses_configured_prompt_variant(monkeypatch):
    calls = _fake_client(monkeypatch)
    monkeypatch.setenv("NLQ_PROMPT", "schema")
    generate("질문", USER)
    assert calls[0]["system"][0]["text"] == system_prompt("schema", USER)


# --- 역할별 거르기 (M5). 정보 노출을 줄이는 장치이고, 권한은 execute()가 강제한다 ---

PERSONAS = load_users()


def _schema_tables(prompt):
    block = prompt.split("\n<schema>\n")[1].split("\n</schema>")[0]
    return set(re.findall(r"^(\w+)\(", block, re.M))


@pytest.mark.parametrize("login", sorted(PERSONAS))
def test_prompt_has_only_readable_tables_and_docs(login):
    user = PERSONAS[login].user
    prompt = system_prompt("okf", user)
    assert _schema_tables(prompt) == set(user.tables)
    for path in KNOWLEDGE.rglob("*.md"):
        if path.name == "README.md":
            continue
        tag = f'<doc path="{path.relative_to(KNOWLEDGE)}">'
        # 문서의 tables가 하나라도 역할 밖이면 뺀다 (docs/architecture.md "지식 층")
        assert (tag in prompt) == (set(doc_tables(path)) <= user.tables), tag


def test_stock_user_prompt_has_no_customer_invoices():
    # 재고 담당은 고객 송장(account_move)을 읽을 수 없다. 열 목록과 account_move 문서가 빠진다.
    # 거르기는 앞머리 tables 기준이라, 다른 문서 본문이 테이블 이름을 언급하는 것까지 지우지는 않는다.
    prompt = system_prompt("okf", PERSONAS["stock.choi"].user)
    assert "account_move(" not in prompt
    assert '<doc path="tables/account_move.md">' not in prompt


def test_user_without_tables_gets_no_schema():
    assert _schema_tables(system_prompt("okf", USER)) == set()


def test_generate_sends_role_filtered_prompt(monkeypatch):
    calls = _fake_client(monkeypatch)
    choi = PERSONAS["stock.choi"].user
    generate("질문", choi)
    assert calls[0]["system"][0]["text"] == system_prompt(user=choi)
    assert "account_move(" not in calls[0]["system"][0]["text"]


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_generate_raises_when_no_sql(monkeypatch, stop_reason):
    _fake_client(monkeypatch, stop_reason=stop_reason)
    with pytest.raises(GenerationError, match=stop_reason):
        generate("질문", USER)


@pytest.mark.skipif(os.environ.get("NLQ_LIVE_API") != "1", reason="NLQ_LIVE_API=1일 때만 Claude API를 부른다")
def test_live_generate_returns_select():
    result = generate("회사 이름 목록", USER)
    assert result.sql.lstrip().upper().startswith(("SELECT", "WITH"))
