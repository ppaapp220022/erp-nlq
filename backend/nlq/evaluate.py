"""평가 문항(eval/questions/)을 돌려 영역별 정확도를 낸다 (M4).

    uv run --directory backend nlq-eval                       # 전체, EVAL_MODEL(기본 Haiku)
    uv run --directory backend nlq-eval --model claude-opus-5-5   # 결과 표용 측정
    uv run --directory backend nlq-eval sales-001 stock-002   # 일부만
    uv run --directory backend nlq-eval --prompt schema       # 비교 기준 1: OKF 묶음 없이
    uv run --directory backend nlq-eval --retries 0           # 자기 수정 없이 (전후 비교용)
    uv run --directory backend nlq-eval --retrieve embedding  # 검색 방식 (기본 keyword, M5 검색 비교)
    uv run --directory backend nlq-eval --clarify off         # 되묻기 없이 (전후 비교용)
    uv run --directory backend nlq-eval --clarify-set         # 되묻기 세트(eval/clarify/): 되묻는지, 기준을 고른 뒤 맞히는지
    uv run --directory backend nlq-eval --enforce rls         # 행 범위를 RLS 정책으로 (기본 guard, M6 비교)
    uv run --directory backend nlq-eval --ci                  # CI 20문항(eval/ci/questions.yaml). 기준보다 적게 맞히면 종료 코드 1

문항마다 ask()로 SQL을 만들어 실행하고(실패하면 오류를 넣어 다시 만든다), 정답 SQL도 같은 사용자로
execute()해 결과를 비교한다. 평가 문항은 기준이 정해진 질문이라, 되물으면 clarification으로 세고 틀린 것으로 본다. DB와 API로 가는 길은 generate()와 execute()뿐이다. 결과는 eval/results/에 JSON으로 남긴다(git 제외).
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
from nlq.prompt import CLARIFY_SETTINGS, DEFAULT_VARIANT, VARIANTS, clarify_enabled, prompt_variant, system_prompt
from nlq.retrieve import DEFAULT_METHOD, METHODS, load_examples, retrieve, retrieve_method
from nlq.scoring import matches
from nlq.settings import ENFORCEMENTS, ROOT, enforcement, eval_today, setting
from nlq.users import load_users

QUESTIONS = ROOT / "eval" / "questions"
CLARIFY = ROOT / "eval" / "clarify"
CI_QUESTIONS = ROOT / "eval" / "ci" / "questions.yaml"
RESULTS = ROOT / "eval" / "results"
AREAS = ["판매", "구매", "재고", "회계"]


@dataclass
class Result:
    id: str
    area: str
    role: str
    # correct | wrong | clarification | generation_error | guard_rejected | execution_error
    status: str
    sql: str | None = None
    error: str | None = None
    seconds: float = 0.0
    # 자기 수정: 다시 만든 횟수와 첫 시도의 오류(마지막 시도만 채점한다)
    retried: int = 0
    first_error: str | None = None
    # 검색: 사용자 메시지에 넣은 예시 id
    examples: list[str] | None = None
    # 되묻기: 되물은 질문과 선택지 (평가 문항에서는 오답, 되묻기 세트에서는 기대한 동작)
    clarification: str | None = None
    options: list[str] | None = None


def load_questions(ids: list[str] | None = None) -> list[dict]:
    questions = [yaml.safe_load(p.read_text()) for p in sorted(QUESTIONS.glob("*.yaml"))]
    if ids:
        missing = set(ids) - {q["id"] for q in questions}
        if missing:
            raise SystemExit(f"없는 문항: {', '.join(sorted(missing))}")
        questions = [q for q in questions if q["id"] in ids]
    return questions


def run_one(q: dict, retries: int = RETRIES, clarified: str | None = None) -> Result:
    user = load_users()[q["role"]].user
    start = time.monotonic()
    result = Result(id=q["id"], area=q.get("area", "되묻기"), role=q["role"], status="wrong")
    # generate()와 같은 호출이라 같은 예시가 나온다(결정적)
    result.examples = [e.id for e in retrieve(q["question"], user)]
    # 정답이 실행되지 않으면 문항 쪽 문제다. 채점하지 않고 멈춘다(test_eval_questions.py가 먼저 잡아야 한다).
    gold = execute(q["gold_sql"], user)
    try:
        attempts = ask(q["question"], user, retries, clarified)
    except GenerationError as e:
        result.status, result.error = "generation_error", str(e)
    else:
        last = attempts[-1]
        if last.clarification is not None:
            result.status = "clarification"
            result.clarification, result.options = last.clarification.question, list(last.clarification.options)
            result.seconds = round(time.monotonic() - start, 1)
            return result
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
        "| 영역 | 정답 | 문항 | 정확도 | 되물음 | 생성 실패 | guard 거부 | 실행 오류 | 재시도 | 재시도로 정답 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for area in [a for a in AREAS if a in summary] + ["전체"]:
        s = summary[area]
        n, ok = s["total"], s.get("correct", 0)
        lines.append(
            f"| {area} | {ok} | {n} | {ok / n:.0%} | {s.get('clarification', 0)} | {s.get('generation_error', 0)} "
            f"| {s.get('guard_rejected', 0)} | {s.get('execution_error', 0)} | {s.get('retried', 0)} | {s.get('fixed', 0)} |"
        )
    return "\n".join(lines)


def prompt_version() -> str:
    # 역할마다 프롬프트가 다르므로 사용자별 프롬프트를 모두 이어 해시한다. 거르는 규칙이 바뀌어도 버전이 바뀐다.
    prompts = (system_prompt(user=p.user) for _, p in sorted(load_users().items()))
    return hashlib.sha256("\n".join(prompts).encode()).hexdigest()[:12]


def examples_version() -> str:
    text = "\n".join(f"{e.id}\n{e.question}\n{e.sql}" for e in load_examples())
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nlq-eval", description="평가 문항 채점")
    parser.add_argument("ids", nargs="*", help="돌릴 문항 id. 없으면 전체")
    parser.add_argument("--model", help=f"Claude 모델 ID (기본: EVAL_MODEL, 없으면 {DEFAULT_MODEL})")
    parser.add_argument("--prompt", choices=VARIANTS, help=f"프롬프트 변형 (기본: NLQ_PROMPT, 없으면 {DEFAULT_VARIANT})")
    parser.add_argument("--retrieve", choices=METHODS, help=f"예시 검색 방식 (기본: NLQ_RETRIEVE, 없으면 {DEFAULT_METHOD})")
    parser.add_argument("--clarify", choices=CLARIFY_SETTINGS, help="되묻기 (기본: NLQ_CLARIFY, 없으면 on)")
    parser.add_argument("--ci", action="store_true", help="CI 20문항(eval/ci/questions.yaml)만 돌리고 min_correct 미만이면 실패")
    parser.add_argument("--clarify-set", action="store_true", help="평가 문항 대신 되묻기 세트(eval/clarify/)를 돌린다")
    parser.add_argument("--enforce", choices=ENFORCEMENTS, help="행 범위를 거는 방식 (기본: NLQ_ENFORCE, 없으면 guard)")
    parser.add_argument("--retries", type=int, default=RETRIES, help=f"실행 실패 시 다시 만드는 횟수 (기본 {RETRIES})")
    parser.add_argument("--jobs", type=int, default=4, help="동시에 돌릴 문항 수")
    args = parser.parse_args(argv)

    if args.model:
        os.environ["EVAL_MODEL"] = args.model
    if args.prompt:
        os.environ["NLQ_PROMPT"] = args.prompt
    if args.retrieve:
        os.environ["NLQ_RETRIEVE"] = args.retrieve
    if args.clarify:
        os.environ["NLQ_CLARIFY"] = args.clarify
    if args.enforce:
        os.environ["NLQ_ENFORCE"] = args.enforce
    if args.clarify_set:
        return clarify_main(args)
    model = setting("EVAL_MODEL", DEFAULT_MODEL)
    variant = prompt_variant()
    method = retrieve_method()
    ci = yaml.safe_load(CI_QUESTIONS.read_text()) if args.ci else None
    questions = load_questions(ci["questions"] if ci else args.ids)
    print(
        f"모델 {model}, 프롬프트 {variant} {prompt_version()}, 검색 {method}, 되묻기 {_clarify_label()}, "
        f"재시도 {args.retries}, 범위 {enforcement()}, 문항 {len(questions)}개",
        file=sys.stderr,
    )
    # 임베딩 모델은 스레드를 띄우기 전에 한 번 적재한다
    retrieve(questions[0]["question"], load_users()[questions[0]["role"]].user)

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
        "retrieve": method,
        "examples_version": examples_version(),
        "clarify": _clarify_label(),
        "retries": args.retries,
        "enforce": enforcement(),
        "today": eval_today(),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-{model}-{variant}-{method}-r{args.retries}{'' if clarify_enabled() else '-noclarify'}{'' if enforcement() == 'guard' else '-' + enforcement()}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(format_summary(summary))
    print(f"\n결과: {path.relative_to(ROOT)}", file=sys.stderr)
    if ci:
        correct = sum(r.status == "correct" for r in results)
        verdict = "통과" if correct >= ci["min_correct"] else "실패"
        print(f"\nCI 평가 {verdict}: {correct}/{len(results)} 정답 (기준 {ci['min_correct']}, 모델 {model})")
        if correct < ci["min_correct"]:
            return 1
    return 0


def _clarify_label() -> str:
    return "on" if clarify_enabled() else "off"


def load_clarify_set(ids: list[str] | None = None) -> list[dict]:
    items = [yaml.safe_load(p.read_text()) for p in sorted(CLARIFY.glob("*.yaml"))]
    return [q for q in items if not ids or q["id"] in ids]


def clarify_main(args: argparse.Namespace) -> int:
    """되묻기 세트: 첫 질문에서 되묻는지(되물음), 고른 기준(answer)을 넣으면 맞히는지(확인 후 정답).

    되묻기를 끄면(--clarify off) 첫 질문에 바로 답하므로, 그 답이 고른 기준과 맞는지가 비교 기준이 된다(첫 답 정답).
    """
    model = setting("EVAL_MODEL", DEFAULT_MODEL)
    items = load_clarify_set(args.ids)
    print(
        f"모델 {model}, 프롬프트 {prompt_variant()} {prompt_version()}, 검색 {retrieve_method()}, "
        f"되묻기 {_clarify_label()}, 되묻기 세트 {len(items)}개",
        file=sys.stderr,
    )
    retrieve(items[0]["question"], load_users()[items[0]["role"]].user)

    def both(q: dict) -> tuple[Result, Result]:
        return run_one(q, args.retries), run_one(q, args.retries, clarified=q["answer"])

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pairs = list(pool.map(both, items))
    asked = sum(first.status == "clarification" for first, _ in pairs)
    direct = sum(first.status == "correct" for first, _ in pairs)
    fixed = sum(second.status == "correct" for _, second in pairs)
    for q, (first, second) in zip(items, pairs):
        what = f"되물음: {first.clarification} {first.options}" if first.status == "clarification" else f"바로 답함({first.status})"
        print(f"{q['id']:<12} {what}\n{'':<12} 기준 '{q['answer']}' → {second.status}", file=sys.stderr)
    record = {
        "model": model,
        "prompt": prompt_variant(),
        "prompt_version": prompt_version(),
        "retrieve": retrieve_method(),
        "clarify": _clarify_label(),
        "retries": args.retries,
        "today": eval_today(),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {"total": len(items), "asked": asked, "correct_first": direct, "correct_after_answer": fixed},
        "results": [{"first": asdict(a), "after_answer": asdict(b)} for a, b in pairs],
    }
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{datetime.now():%Y%m%d-%H%M%S}-{model}-clarify-set-{_clarify_label()}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(
        f"| 문항 | 되물음 | 첫 답 정답 | 기준을 고른 뒤 정답 |\n|---|---|---|---|\n| {len(items)} | {asked} | {direct} | {fixed} |"
    )
    print(f"\n결과: {path.relative_to(ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
