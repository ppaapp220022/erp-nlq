"""되묻기 (M5). 업무 기준이 갈리는 질문이면 SQL 대신 질문과 선택지를 돌려주고, 고른 기준을 넣으면 SQL을 만든다.

되묻기 세트(eval/clarify/)의 형식과 정답 SQL 실행도 여기서 본다. 정답 실행은 로컬 DB가 있을 때만 돈다.
"""

import importlib
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
import yaml
from fastapi.testclient import TestClient

from nlq import Clarification, GeneratedSQL, GenerationError, api, ask, cli, execute, generate
from nlq.prompt import CLARIFY_RULE, system_prompt, user_message
from nlq.settings import ROOT, readonly_conninfo
from nlq.users import load_users

generate_module = importlib.import_module("nlq.generate")
ask_module = importlib.import_module("nlq.ask")
PERSONAS = load_users()
USER = PERSONAS["admin"].user
CLARIFY_SET = sorted((ROOT / "eval" / "clarify").glob("*.yaml"))
FIELDS = {"id", "role", "question", "expect", "answer", "gold_sql", "order_matters", "notes"}


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


def _fake(monkeypatch, **answer):
    calls = []

    def parse(**kwargs):
        calls.append(kwargs)
        fmt = kwargs["output_format"]
        fields = {"kind": "sql", "sql": "", "clarification": "", "options": [], **answer}
        if fmt is generate_module._Answer:
            fields = {"sql": answer.get("sql", "SELECT 1")}
        return SimpleNamespace(stop_reason="end_turn", parsed_output=fmt(**fields))

    monkeypatch.setattr(generate_module, "_client", lambda: SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    return calls


# --- 프롬프트와 생성 ---


def test_rule_is_in_prompt_only_when_on(monkeypatch):
    monkeypatch.setenv("NLQ_CLARIFY", "on")
    assert CLARIFY_RULE in system_prompt(user=USER)
    monkeypatch.setenv("NLQ_CLARIFY", "off")
    assert CLARIFY_RULE not in system_prompt(user=USER)
    monkeypatch.setenv("NLQ_CLARIFY", "maybe")
    with pytest.raises(RuntimeError, match="NLQ_CLARIFY"):
        system_prompt(user=USER)


def test_generate_returns_clarification(monkeypatch):
    monkeypatch.setenv("NLQ_CLARIFY", "on")
    calls = _fake(monkeypatch, kind="clarify", clarification="주문 기준인가요, 송장 기준인가요?", options=[" 주문 기준", "송장 기준 "])
    result = generate("판매액", USER)
    assert result == GeneratedSQL(sql="", model=result.model, clarification=Clarification("주문 기준인가요, 송장 기준인가요?", ("주문 기준", "송장 기준")))
    assert calls[0]["output_format"] is generate_module._AnswerOrClarify


@pytest.mark.parametrize(
    "answer",
    [
        {"kind": "clarify", "clarification": "", "options": ["a", "b"]},  # 질문 없음
        {"kind": "clarify", "clarification": "어느 쪽?", "options": ["a"]},  # 선택지 하나
        {"kind": "clarify", "clarification": "어느 쪽?", "options": ["a", "b", "c", "d", "e"]},  # 너무 많음
        {"kind": "sql", "sql": "  "},  # 빈 SQL
    ],
)
def test_malformed_answer_is_generation_error(monkeypatch, answer):
    monkeypatch.setenv("NLQ_CLARIFY", "on")
    _fake(monkeypatch, **answer)
    with pytest.raises(GenerationError):
        generate("판매액", USER)


@pytest.mark.parametrize("kwargs", [{"clarified": "주문 기준"}, {"failed": ask_module.Failed(sql="SELECT x", error="e")}])
def test_no_second_question_after_answer_or_failure(monkeypatch, kwargs):
    # 기준을 받은 뒤와 자기 수정 때는 SQL만 받는 형식이라 다시 물을 수 없다
    monkeypatch.setenv("NLQ_CLARIFY", "on")
    calls = _fake(monkeypatch, sql="SELECT 2")
    assert generate("판매액", USER, **kwargs).sql == "SELECT 2"
    assert calls[0]["output_format"] is generate_module._Answer


def test_off_never_asks(monkeypatch):
    monkeypatch.setenv("NLQ_CLARIFY", "off")
    calls = _fake(monkeypatch, sql="SELECT 3")
    assert generate("판매액", USER).sql == "SELECT 3"
    assert calls[0]["output_format"] is generate_module._Answer


def test_clarified_basis_goes_to_user_message():
    message = user_message("판매액", USER, clarified="송장 기준")
    assert "확인한 기준: 송장 기준" in message
    assert "송장 기준" not in user_message("판매액", USER)


# --- ask·API·CLI ---


def test_ask_stops_at_clarification(monkeypatch):
    c = Clarification("어느 쪽?", ("a", "b"))
    monkeypatch.setattr(ask_module, "generate", lambda q, user, failed, clarified: GeneratedSQL("", "m", c))
    monkeypatch.setattr(ask_module, "execute", lambda *_: pytest.fail("되물으면 실행하지 않는다"))
    (attempt,) = ask.ask("판매액", USER)
    assert attempt.clarification == c and attempt.rows is None


def test_ask_passes_clarified(monkeypatch):
    seen = []
    monkeypatch.setattr(ask_module, "generate", lambda q, user, failed, clarified: seen.append(clarified) or GeneratedSQL("SELECT 1", "m"))
    monkeypatch.setattr(ask_module, "execute", lambda sql, user: "rows")
    ask.ask("판매액", USER, clarified="주문 기준")
    assert seen == ["주문 기준"]


def test_api_returns_clarification_and_accepts_basis(monkeypatch):
    seen = []

    def fake(question, user, failed, clarified):
        seen.append(clarified)
        if clarified is None:
            return GeneratedSQL("", "m", Clarification("어느 쪽?", ("주문 기준", "송장 기준")))
        return GeneratedSQL("SELECT 1", "m")

    monkeypatch.setattr(api, "generate", fake)
    client = TestClient(api.app)
    first = client.post("/generate", json={"question": "판매액", "user": "admin"}).json()
    assert first == {"sql": "", "model": "m", "clarification": {"question": "어느 쪽?", "options": ["주문 기준", "송장 기준"]}}
    second = client.post("/generate", json={"question": "판매액", "user": "admin", "clarified": "송장 기준"}).json()
    assert second["sql"] == "SELECT 1" and second["clarification"] is None
    assert seen == [None, "송장 기준"]
    assert client.post("/generate", json={"question": "q", "user": "admin", "clarified": "x" * 301}).status_code == 422


def test_cli_prints_options_when_not_a_terminal(monkeypatch, capsys):
    c = Clarification("어느 쪽?", ("주문 기준", "송장 기준"))
    monkeypatch.setattr(ask_module, "generate", lambda q, user, failed, clarified: GeneratedSQL("", "m", c))
    assert cli.main(["판매액", "--user", "admin"]) == 2
    out = capsys.readouterr()
    assert "되물음: 어느 쪽?" in out.out and "1. 주문 기준" in out.out and "--clarified" in out.err


# --- 되묻기 세트 (eval/clarify/) ---


def test_clarify_set_exists():
    assert len(CLARIFY_SET) >= 8


@pytest.mark.parametrize("path", CLARIFY_SET, ids=lambda p: p.stem)
def test_clarify_set_format(path):
    q = yaml.safe_load(path.read_text())
    assert set(q) == FIELDS
    assert q["id"] == path.stem
    assert q["role"] in PERSONAS
    assert isinstance(q["order_matters"], bool)


def test_clarify_set_not_in_examples():
    # 절대 규칙 4: 평가에 쓰는 세트라 예시에 두지 않는다
    examples = {yaml.safe_load(p.read_text())["question"].strip() for p in (ROOT / "eval" / "examples").glob("*.yaml")}
    assert not examples & {yaml.safe_load(p.read_text())["question"].strip() for p in CLARIFY_SET}


@db
@pytest.mark.parametrize("path", CLARIFY_SET, ids=lambda p: p.stem)
def test_clarify_gold_sql_runs(path):
    q = yaml.safe_load(path.read_text())
    rows = execute(q["gold_sql"], PERSONAS[q["role"]].user)
    assert rows.rows and not rows.truncated
