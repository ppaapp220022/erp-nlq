"""평가 문항(eval/questions/)을 돌려 영역별 정확도를 낸다 (M4).

    uv run --directory backend nlq-eval                       # 전체, EVAL_MODEL(기본 Haiku)
    uv run --directory backend nlq-eval --model claude-opus-5-5   # 결과 표용 측정
    uv run --directory backend nlq-eval sales-001 stock-002   # 일부만
    uv run --directory backend nlq-eval --prompt schema       # 비교 기준 1: OKF 묶음 없이
    uv run --directory backend nlq-eval --retries 0           # 자기 수정 없이 (전후 비교용)

문항마다 ask()로 SQL을 만들어 실행하고(실패하면 오류를 넣어 다시 만든다), 정답 SQL도 같은 사용자로
execute()해 결과를 비교한다. DB와 API로 가는 길은 generate()와 execute()뿐이다. 결과는 eval/results/에 JSON으로 남긴다(git 제외).
Haiku 점수와 Opus 점수를 섞지 않는다. 결과 파일에 모델과 프롬프트 변형·버전이 함께 남는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import yaml

from nlq import GenerationError, execute
from nlq.ask import RETRIES, ask
from nlq.generate import DEFAULT_MODEL
from nlq.models import GuardError
from nlq.prompt import DEFAULT_VARIANT, VARIANTS, prompt_variant, system_prompt
from nlq.scoring import matches
from nlq.settings import ROOT, eval_today, setting
from nlq.users import load_users

QUESTIONS = ROOT / "eval" / "questions"
RESULTS = ROOT / "eval" / "results"
AREAS = ["판매", "구매", "재고", "회계"]


@dataclass
class Result:
    id: str
    area: str
    role: str
    # correct | wrong | generation_error | guard_rejected | execution_error
    status: str
    sql: str | None = None
    error: str | None = None
    seconds: float = 0.0
    # 자기 수정: 다시 만든 횟수와 첫 시도의 오류(마지막 시도만 채점한다)
    retried: int = 0
    first_error: str | None = None


def load_questions(ids: list[str] | None = None) -> list[dict]:
    questions = [yaml.safe_load(p.read_text()) for p in sorted(QUESTIONS.glob("*.yaml"))]
    if ids:
        missing = set(ids) - {q["id"] for q in questions}
        if missing:
            raise SystemExit(f"없는 문항: {', '.join(sorted(missing))}")
        questions = [q for q in questions if q["id"] in ids]
    return questions


def run_one(q: dict, retries: int = RETRIES) -> Result:
    user = load_users()[q["role"]].user
    start = time.monotonic()
    result = Result(id=q["id"], area=q["area"], role=q["role"], status="wrong")
    # 정답이 실행되지 않으면 문항 쪽 문제다. 채점하지 않고 멈춘다(test_eval_questions.py가 먼저 잡아야 한다).
    gold = execute(q["gold_sql"], user)
    try:
        attempts = ask(q["question"], user, retries)
    except GenerationError as e:
        result.status, result.error = "generation_error", str(e)
    else:
        last = attempts[-1]
        result.sql, result.retried = last.sql, len(attempts) - 1
        if result.retried:
            result.first_error = str(attempts[0].error)
        if isinstance(last.error, GuardError):
            result.status, result.error = "guard_rejected", str(last.error)
        elif last.error is not None:
            result.status, result.error = "execution_error", str(last.error)
        else:
            result.status = "correct" if matches(gold, last.rows, q["order_matters"]) else "wrong"
    result.seconds = round(time.monotonic() - start, 1)
    return result


def summarize(results: list[Result]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        for key in (r.area, "전체"):
            summary[key]["total"] += 1
            summary[key][r.status] += 1
            if r.retried:
                summary[key]["retried"] += 1
                summary[key]["fixed"] += r.status == "correct"
    return {k: dict(v) for k, v in summary.items()}


def format_summary(summary: dict[str, dict[str, int]]) -> str:
    lines = [
        "| 영역 | 정답 | 문항 | 정확도 | 생성 실패 | guard 거부 | 실행 오류 | 재시도 | 재시도로 정답 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for area in [a for a in AREAS if a in summary] + ["전체"]:
        s = summary[area]
        n, ok = s["total"], s.get("correct", 0)
        lines.append(
            f"| {area} | {ok} | {n} | {ok / n:.0%} | {s.get('generation_error', 0)} "
            f"| {s.get('guard_rejected', 0)} | {s.get('execution_error', 0)} | {s.get('retried', 0)} | {s.get('fixed', 0)} |"
        )
    return "\n".join(lines)


def prompt_version() -> str:
    # 역할마다 프롬프트가 다르므로 사용자별 프롬프트를 모두 이어 해시한다. 거르는 규칙이 바뀌어도 버전이 바뀐다.
    prompts = (system_prompt(user=p.user) for _, p in sorted(load_users().items()))
    return hashlib.sha256("\n".join(prompts).encode()).hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nlq-eval", description="평가 문항 채점")
    parser.add_argument("ids", nargs="*", help="돌릴 문항 id. 없으면 전체")
    parser.add_argument("--model", help=f"Claude 모델 ID (기본: EVAL_MODEL, 없으면 {DEFAULT_MODEL})")
    parser.add_argument("--prompt", choices=VARIANTS, help=f"프롬프트 변형 (기본: NLQ_PROMPT, 없으면 {DEFAULT_VARIANT})")
    parser.add_argument("--retries", type=int, default=RETRIES, help=f"실행 실패 시 다시 만드는 횟수 (기본 {RETRIES})")
    parser.add_argument("--jobs", type=int, default=4, help="동시에 돌릴 문항 수")
    args = parser.parse_args(argv)

    if args.model:
        os.environ["EVAL_MODEL"] = args.model
    if args.prompt:
        os.environ["NLQ_PROMPT"] = args.prompt
    model = setting("EVAL_MODEL", DEFAULT_MODEL)
    variant = prompt_variant()
    questions = load_questions(args.ids)
    print(
        f"모델 {model}, 프롬프트 {variant} {prompt_version()}, 재시도 {args.retries}, 문항 {len(questions)}개",
        file=sys.stderr,
    )

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda q: run_one(q, args.retries), questions))
    for r in results:
        detail = f"  {r.error}" if r.error else ""
        if r.retried:
            detail += f"  (재시도, 첫 오류: {r.first_error})"
        print(f"{r.id:<14} {r.status:<17} {r.seconds:>5}s{detail}", file=sys.stderr)

    summary = summarize(results)
    record = {
        "model": model,
        "prompt": variant,
        "prompt_version": prompt_version(),
        "retries": args.retries,
        "today": eval_today(),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-{model}-{variant}-r{args.retries}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(format_summary(summary))
    print(f"\n결과: {path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
