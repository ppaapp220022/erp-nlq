"""generate()와 프롬프트 테스트. Claude API를 부르지 않는다.

실제 호출 확인은 NLQ_LIVE_API=1일 때만 돈다(비용이 들어 CI에서는 돌리지 않는다).
"""

import importlib
import os
import re
from types import SimpleNamespace

import pytest

from nlq import GenerationError, User, generate
from nlq.prompt import KNOWLEDGE, SCHEMA, VARIANTS, system_prompt, user_message
from nlq.settings import ROOT, eval_today

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


def test_generate_uses_configured_prompt_variant(monkeypatch):
    calls = _fake_client(monkeypatch)
    monkeypatch.setenv("NLQ_PROMPT", "schema")
    generate("질문", USER)
    assert calls[0]["system"][0]["text"] == system_prompt("schema")


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_generate_raises_when_no_sql(monkeypatch, stop_reason):
    _fake_client(monkeypatch, stop_reason=stop_reason)
    with pytest.raises(GenerationError, match=stop_reason):
        generate("질문", USER)


@pytest.mark.skipif(os.environ.get("NLQ_LIVE_API") != "1", reason="NLQ_LIVE_API=1일 때만 Claude API를 부른다")
def test_live_generate_returns_select():
    result = generate("회사 이름 목록", USER)
    assert result.sql.lstrip().upper().startswith(("SELECT", "WITH"))
