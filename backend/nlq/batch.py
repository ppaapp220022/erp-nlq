"""평가용 배치 생성 (Message Batches API). 동기 호출보다 토큰 단가가 50% 싸고, 응답은 비동기로 온다.

nlq-eval --batch만 쓴다. 대화형 경로(nlq, nlq-api)와 CI(--ci)는 generate()를 그대로 쓴다.
요청은 generate()와 같은 인자(nlq.generate.request)로 만들고, 결과는 같은 검사(to_generated)를 거친다.
배치는 생성만 대신한다. SQL 실행은 받은 뒤 ask.run_generated() → execute()로 한다(CLAUDE.md 절대 규칙 1·2).

자기 수정처럼 앞 결과가 있어야 만드는 요청은 단계마다 배치를 하나씩 보낸다(run_stages).
"""

from __future__ import annotations

import importlib
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from anthropic import transform_schema
from pydantic import TypeAdapter, ValidationError

from nlq.ask import Attempt, run_generated
from nlq.generate import record_usage, request, to_generated
from nlq.models import Failed, GeneratedSQL, GenerationError, User

POLL_SECONDS = 30
# nlq 패키지가 generate 함수를 같은 이름으로 내보내므로 모듈은 따로 가져온다(테스트가 _client를 바꿔 끼운다).
_generate = importlib.import_module("nlq.generate")


@dataclass(frozen=True)
class Job:
    """배치로 만들 질문 하나. clarified는 되묻기 세트에서 고른 기준이다."""

    question: str
    user: User
    clarified: str | None = None


@dataclass
class Outcome:
    """Job 하나의 결과. ask()가 돌려주는 시도 목록과 같거나, 생성 실패다."""

    attempts: list[Attempt] = field(default_factory=list)
    error: GenerationError | None = None
    finished: float = 0.0  # 마지막 단계가 끝난 시각(time.monotonic)


def params(job: Job, failed: Failed | None = None) -> tuple[dict, type]:
    """배치 요청 인자. messages.parse()가 output_format을 바꾸는 방식대로 출력 형식을 output_config에 넣는다."""
    params, output_format = request(job.question, job.user, failed, job.clarified)
    schema = transform_schema(TypeAdapter(output_format).json_schema())
    params["output_config"] = {**params["output_config"], "format": {"type": "json_schema", "schema": schema}}
    return params, output_format


def to_result(entry: object, output_format: type, model: str) -> GeneratedSQL:
    """배치 결과 한 줄을 GeneratedSQL로. 성공이 아니면(errored·expired·canceled) GenerationError."""
    result = entry.result
    if result.type != "succeeded":
        detail = ""
        if result.type == "errored":
            error = getattr(getattr(result, "error", None), "error", None)
            detail = f", {getattr(error, 'type', 'unknown')}"
        raise GenerationError(f"배치 요청이 끝나지 못했다 ({result.type}{detail})")
    message = result.message
    record_usage(getattr(message, "usage", None))
    text = "".join(b.text for b in message.content if b.type == "text")
    answer = None
    if message.stop_reason == "end_turn":
        try:
            answer = output_format.model_validate_json(text)
        except ValidationError as e:
            raise GenerationError("배치 응답이 출력 형식에 맞지 않는다") from e
    return to_generated(message.stop_reason, answer, model)


def generate_batch(
    requests: list[tuple[Job, Failed | None]],
    poll: float = POLL_SECONDS,
    log: Callable[[str], None] = lambda m: print(m, file=sys.stderr),
) -> tuple[str, list[GeneratedSQL | GenerationError]]:
    """요청마다 GeneratedSQL이나 GenerationError를 같은 순서로 돌려준다. 배치 id도 함께 돌려준다."""
    built = [params(job, failed) for job, failed in requests]
    client = _generate._client()
    # custom_id는 영숫자·_·-만 되므로 위치를 쓴다. 결과는 순서가 없어 custom_id로 맞춘다.
    batch = client.messages.batches.create(
        requests=[{"custom_id": f"r{i}", "params": p} for i, (p, _) in enumerate(built)]
    )
    log(f"배치 {batch.id}: 요청 {len(built)}개")
    while batch.processing_status != "ended":
        time.sleep(poll)
        batch = client.messages.batches.retrieve(batch.id)
        counts = batch.request_counts
        log(f"배치 {batch.id}: {batch.processing_status}, 처리 중 {counts.processing}, 완료 {counts.succeeded}")
    out: list[GeneratedSQL | GenerationError] = [GenerationError("배치 결과에 없다")] * len(built)
    for entry in client.messages.batches.results(batch.id):
        index = int(entry.custom_id.removeprefix("r"))
        p, output_format = built[index]
        try:
            out[index] = to_result(entry, output_format, p["model"])
        except GenerationError as e:
            out[index] = e
    return batch.id, out


def run_stages(
    jobs: list[Job],
    retries: int,
    execute_all: Callable[[Callable[[int], Attempt], Iterable[int]], list[Attempt]] | None = None,
    poll: float = POLL_SECONDS,
) -> tuple[list[Outcome], list[str]]:
    """ask()를 단계별 배치로 돈다. 단계 k의 배치에는 k번째 시도가 필요한 문항만 들어간다.

    ask()와 같은 규칙이다: 되물으면 멈추고, 실행되면 멈추고, 실행 실패면 오류를 넣어 retries번까지 다시 만든다.
    execute_all은 실행을 동시에 돌리는 함수(평가의 스레드 풀)이고, 없으면 차례로 실행한다.
    """
    outcomes = [Outcome() for _ in jobs]
    failed: dict[int, Failed | None] = {i: None for i in range(len(jobs))}
    batch_ids: list[str] = []
    run = execute_all or (lambda f, ids: [f(i) for i in ids])
    for _ in range(retries + 1):
        pending = list(failed)
        if not pending:
            break
        batch_id, generated = generate_batch([(jobs[i], failed[i]) for i in pending], poll)
        batch_ids.append(batch_id)
        by_index = dict(zip(pending, generated))
        to_run = []
        for i, g in by_index.items():
            if isinstance(g, GenerationError):
                outcomes[i].error = g
                outcomes[i].finished = time.monotonic()
                del failed[i]
            else:
                to_run.append(i)
        attempts = run(lambda i: run_generated(by_index[i], jobs[i].user), to_run)
        for i, attempt in zip(to_run, attempts):
            outcomes[i].attempts.append(attempt)
            outcomes[i].finished = time.monotonic()
            if attempt.error is None:
                del failed[i]
            else:
                failed[i] = Failed(sql=attempt.sql, error=str(attempt.error))
    return outcomes, batch_ids
