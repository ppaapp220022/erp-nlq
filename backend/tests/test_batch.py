"""배치 평가(nlq/batch.py) 테스트. Claude API와 DB를 부르지 않는다.

배치 결과 파싱, 실패·만료 문항 처리, 단계별 배치(자기 수정), 동기 요청과 같은 인자인지 본다.
"""

import importlib
import json
from types import SimpleNamespace

import pytest

from nlq import GenerationError, User
from nlq.batch import Job, generate_batch, params, run_stages, to_result
from nlq.models import ExecutionError, GuardError, Rows

generate_module = importlib.import_module("nlq.generate")
ask_module = importlib.import_module("nlq.ask")
evaluate_module = importlib.import_module("nlq.evaluate")

USER = User(odoo_uid=6, login="demo", company_ids=(1,))


def _message(text, stop_reason="end_turn", usage=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
        usage=usage or SimpleNamespace(input_tokens=10, cache_creation_input_tokens=0, cache_read_input_tokens=90, output_tokens=5),
    )


def _ok(custom_id, payload, **kw):
    message = _message(json.dumps(payload) if isinstance(payload, dict) else payload, **kw)
    return SimpleNamespace(custom_id=custom_id, result=SimpleNamespace(type="succeeded", message=message))


def _not_ok(custom_id, kind, error_type="api_error"):
    result = SimpleNamespace(type=kind)
    if kind == "errored":
        result.error = SimpleNamespace(error=SimpleNamespace(type=error_type))
    return SimpleNamespace(custom_id=custom_id, result=result)


class FakeBatches:
    """batches.create/retrieve/results. respond(요청 목록) → 결과 목록. 결과는 일부러 거꾸로 돌려준다."""

    def __init__(self, respond, polls=1):
        self.respond, self.polls, self.created, self.results_for = respond, polls, [], {}

    def create(self, requests):
        self.created.append(requests)
        batch_id = f"msgbatch_{len(self.created)}"
        self.results_for[batch_id] = list(reversed(self.respond(requests)))
        self._left = self.polls
        return self._batch(batch_id, "in_progress")

    def retrieve(self, batch_id):
        self._left -= 1
        return self._batch(batch_id, "ended" if self._left <= 0 else "in_progress")

    def results(self, batch_id):
        return iter(self.results_for[batch_id])

    @staticmethod
    def _batch(batch_id, status):
        counts = SimpleNamespace(processing=0, succeeded=0)
        return SimpleNamespace(id=batch_id, processing_status=status, request_counts=counts)


@pytest.fixture(autouse=True)
def no_real_client(monkeypatch):
    # 가짜를 끼우지 않은 테스트가 실제 배치를 만들지 않게 막는다(배치는 만들면 비용이 든다)
    monkeypatch.setattr(generate_module, "_client", lambda: pytest.fail("실제 Claude API를 부르면 안 된다"))


@pytest.fixture
def fake_batches(monkeypatch):
    def install(respond, polls=1):
        batches = FakeBatches(respond, polls)
        client = SimpleNamespace(messages=SimpleNamespace(batches=batches))
        monkeypatch.setattr(generate_module, "_client", lambda: client)
        return batches

    return install


SQL = {"sql": "SELECT 1"}


# --- 요청 ---


def test_batch_params_match_sync_request_plus_output_format():
    # 동기 경로(messages.parse)와 같은 모델·시스템 프롬프트(캐시 지점 포함)·사용자 메시지를 보낸다
    sync, fmt = generate_module.request("질문", USER)
    batch, batch_fmt = params(Job("질문", USER))
    assert fmt is batch_fmt
    strip = lambda p: {k: v for k, v in p.items() if k != "output_config"}  # noqa: E731
    assert strip(batch) == strip(sync)
    assert batch["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert batch["output_config"]["effort"] == sync["output_config"]["effort"]
    assert batch["output_config"]["format"]["type"] == "json_schema"
    assert "properties" in batch["output_config"]["format"]["schema"]


def test_batch_params_carry_failed_attempt_and_sql_only_format():
    from nlq import Failed

    batch, fmt = params(Job("질문", USER), Failed(sql="SELECT bad", error="oops"))
    assert fmt is generate_module._Answer
    assert "SELECT bad" in batch["messages"][0]["content"]


# --- 결과 파싱 ---


def test_to_result_parses_sql_and_clarification():
    assert to_result(_ok("r0", {"sql": " SELECT 2 \n"}), generate_module._Answer, "m").sql == "SELECT 2"
    clarify = {"kind": "clarify", "sql": "", "clarification": "주문 기준인가요?", "options": ["주문", "송장"]}
    generated = to_result(_ok("r0", clarify), generate_module._AnswerOrClarify, "m")
    assert generated.sql == "" and generated.clarification.options == ("주문", "송장")


@pytest.mark.parametrize(
    "entry, match",
    [
        (_not_ok("r0", "errored", "overloaded_error"), "errored, overloaded_error"),
        (_not_ok("r0", "expired"), "expired"),
        (_not_ok("r0", "canceled"), "canceled"),
        (_ok("r0", "not json"), "출력 형식"),
        (_ok("r0", {"sql": "  "}), "비어"),
        (_ok("r0", "", stop_reason="max_tokens"), "max_tokens"),
        (_ok("r0", "", stop_reason="refusal"), "refusal"),
    ],
)
def test_to_result_failures_become_generation_errors(entry, match):
    with pytest.raises(GenerationError, match=match):
        to_result(entry, generate_module._Answer, "m")


def test_generate_batch_matches_results_by_custom_id_and_marks_missing(fake_batches):
    # 결과는 순서가 없다. r1은 만료, r2는 결과에 없다
    def respond(requests):
        return [_ok("r0", {"sql": "SELECT 0"}), _not_ok("r1", "expired")]

    batches = fake_batches(respond, polls=2)
    jobs = [(Job(f"질문{i}", USER, clarified="기준"), None) for i in range(3)]
    batch_id, out = generate_batch(jobs, poll=0, log=lambda m: None)
    assert batch_id == "msgbatch_1"
    assert [r["custom_id"] for r in batches.created[0]] == ["r0", "r1", "r2"]
    assert out[0].sql == "SELECT 0"
    assert isinstance(out[1], GenerationError) and "expired" in str(out[1])
    assert isinstance(out[2], GenerationError) and "없다" in str(out[2])


def test_generate_batch_records_usage(fake_batches):
    before = generate_module.usage_totals()["cache_read_input_tokens"]
    fake_batches(lambda reqs: [_ok(r["custom_id"], SQL) for r in reqs])
    generate_batch([(Job("q", USER, "기준"), None)] * 2, poll=0, log=lambda m: None)
    assert generate_module.usage_totals()["cache_read_input_tokens"] - before == 180


# --- 단계별 배치: ask()와 같은 규칙, 실행은 execute() ---


def _rows():
    return Rows(columns=["x"], rows=[(1,)], executed_sql="SELECT 1")


def test_run_stages_retries_only_failed_and_executes_every_sql(fake_batches, monkeypatch):
    executed = []

    def execute(sql, user):
        executed.append((sql, user.login))
        if sql == "SELECT bad":
            raise GuardError("허용되지 않은 테이블")
        return _rows()

    monkeypatch.setattr(ask_module, "execute", execute)

    def respond(requests):
        out = []
        for r in requests:
            content = r["params"]["messages"][0]["content"]
            fixed = "previous_sql" in content
            sql = "SELECT good" if fixed or "좋은" in content else "SELECT bad"
            out.append(_ok(r["custom_id"], {"sql": sql}))
        return out

    batches = fake_batches(respond)
    jobs = [Job("좋은 질문", USER, "기준"), Job("나쁜 질문", USER, "기준")]
    outcomes, batch_ids = run_stages(jobs, retries=1, poll=0)
    # 두 번째 배치에는 실패한 문항 하나만, 오류를 담아 들어간다
    assert batch_ids == ["msgbatch_1", "msgbatch_2"]
    assert len(batches.created[1]) == 1
    assert "허용되지 않은 테이블" in batches.created[1][0]["params"]["messages"][0]["content"]
    assert [len(o.attempts) for o in outcomes] == [1, 2]
    assert outcomes[1].attempts[-1].error is None and outcomes[1].attempts[0].error is not None
    assert executed == [("SELECT good", "demo"), ("SELECT bad", "demo"), ("SELECT good", "demo")]


def test_run_stages_stops_after_retries(fake_batches, monkeypatch):
    def execute(sql, user):
        raise ExecutionError("syntax error")

    monkeypatch.setattr(ask_module, "execute", execute)
    fake_batches(lambda reqs: [_ok(r["custom_id"], {"sql": "SELECT x"}) for r in reqs])
    outcomes, batch_ids = run_stages([Job("q", USER, "기준")], retries=1, poll=0)
    assert len(batch_ids) == 2 and len(outcomes[0].attempts) == 2
    assert outcomes[0].attempts[-1].error is not None


def test_run_stages_expired_request_is_generation_error_and_not_executed(fake_batches, monkeypatch):
    monkeypatch.setattr(ask_module, "execute", lambda sql, user: pytest.fail("실행하면 안 된다"))
    fake_batches(lambda reqs: [_not_ok(r["custom_id"], "expired") for r in reqs])
    outcomes, batch_ids = run_stages([Job("q", USER)], retries=1, poll=0)
    assert batch_ids == ["msgbatch_1"]
    assert isinstance(outcomes[0].error, GenerationError) and outcomes[0].attempts == []


def test_run_stages_clarification_is_not_executed_or_retried(fake_batches, monkeypatch):
    monkeypatch.setattr(ask_module, "execute", lambda sql, user: pytest.fail("실행하면 안 된다"))
    clarify = {"kind": "clarify", "sql": "", "clarification": "기준은?", "options": ["a", "b"]}
    fake_batches(lambda reqs: [_ok(r["custom_id"], clarify) for r in reqs])
    outcomes, batch_ids = run_stages([Job("q", USER)], retries=1, poll=0)
    assert len(batch_ids) == 1 and outcomes[0].attempts[0].clarification.question == "기준은?"


# --- 평가 채점: 배치 결과도 같은 score()를 거친다 ---


def test_score_handles_batch_outcomes(monkeypatch):
    monkeypatch.setattr(evaluate_module, "execute", lambda sql, user: _rows())
    q = {"id": "sales-001", "area": "판매", "role": "admin", "question": "q", "gold_sql": "SELECT 1", "order_matters": False}
    ok = evaluate_module.score(q, [ask_module.Attempt(sql="SELECT 1", model="m", rows=_rows())], 1.0)
    assert ok.status == "correct"
    expired = evaluate_module.score(q, GenerationError("배치 요청이 끝나지 못했다 (expired)"), 1.0)
    assert expired.status == "generation_error" and "expired" in expired.error


def test_batch_is_not_allowed_with_ci():
    with pytest.raises(SystemExit):
        evaluate_module.main(["--batch", "--ci"])
