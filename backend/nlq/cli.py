"""터미널에서 질문 → SQL → 결과 표까지 돌린다 (M2 점검용).

    uv run --directory backend nlq "회사별 이번 달 매출" --user sales.kim
    uv run --directory backend nlq --user stock.choi          # 질문을 한 줄씩 입력
    uv run --directory backend nlq --sql "SELECT 1"           # 생성 없이 실행만 (정답 SQL 확인용)

DB와 API로 가는 길은 generate()와 execute()뿐이다. 이 파일은 그 둘(질문은 ask()로 묶어)을 부르고 출력만 한다.
실행이 실패하면 오류를 넣어 SQL을 한 번 다시 만든다(자기 수정, nlq/ask.py).
업무 기준이 갈리는 질문이면 되묻는다. 터미널이면 번호로 고르고, 아니면 --clarified로 기준을 넣어 다시 부른다.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal

from nlq import Clarification, ExecutionError, GenerationError, Rows, execute, generate
from nlq.ask import ask
from nlq.users import Persona, load_users

DEFAULT_USER = "sales.kim"
MAX_CELL = 40


def main(argv: list[str] | None = None) -> int:
    users = load_users()
    parser = argparse.ArgumentParser(prog="nlq", description="ERP 자연어 질의")
    parser.add_argument("question", nargs="?", help="질문. 없으면 한 줄씩 입력받는다")
    parser.add_argument("--user", default=DEFAULT_USER, choices=sorted(users), help=f"질문하는 사용자 (기본 {DEFAULT_USER})")
    parser.add_argument("--sql", help="생성하지 않고 이 SQL을 바로 실행한다")
    parser.add_argument("--no-run", action="store_true", help="SQL만 만들고 실행하지 않는다")
    parser.add_argument("--clarified", help="되물음에 대한 답(고른 기준). 주면 되묻지 않고 SQL을 만든다")
    parser.add_argument("--users", action="store_true", help="고를 수 있는 사용자 목록")
    args = parser.parse_args(argv)

    if args.users:
        for login, p in users.items():
            print(f"{login:<12} {_pad(p.role, 10)} uid={p.user.odoo_uid} 회사={list(p.user.company_ids)}")
        return 0

    persona = users[args.user]
    print(f"사용자: {args.user} ({persona.role})", file=sys.stderr)
    if args.sql:
        return _run(args.sql, persona)
    if args.question:
        return _ask(args.question, persona, run=not args.no_run, clarified=args.clarified)

    status = 0
    for question in _questions():
        status = _ask(question, persona, run=not args.no_run) or status
    return status


def _questions():
    while True:
        try:
            line = input("질문> " if sys.stdin.isatty() else "")
        except EOFError:
            return
        if line.strip():
            yield line.strip()


def _ask(question: str, persona: Persona, *, run: bool, clarified: str | None = None) -> int:
    try:
        if not run:
            generated = generate(question, persona.user, None, clarified)
            if generated.clarification is not None:
                return _clarify(question, persona, generated.clarification, run=run)
            print(f"-- {generated.model}\n{generated.sql}\n", flush=True)
            return 0
        attempts = ask(question, persona.user, clarified=clarified)
    except GenerationError as e:
        print(f"생성 실패: {e}", file=sys.stderr)
        return 1
    if attempts[0].clarification is not None:
        return _clarify(question, persona, attempts[0].clarification, run=run)
    for i, attempt in enumerate(attempts):
        if i:
            print("-- 실행 실패로 오류를 넣어 다시 만들었다", file=sys.stderr)
        print(f"-- {attempt.model}\n{attempt.sql}\n", flush=True)
        if attempt.error is not None:
            print(f"실행 실패: {attempt.error}", file=sys.stderr)
    last = attempts[-1]
    if last.rows is None:
        return 1
    _print_rows(last.rows)
    return 0


def _clarify(question: str, persona: Persona, clarification: Clarification, *, run: bool) -> int:
    print(f"되물음: {clarification.question}", flush=True)
    for i, option in enumerate(clarification.options, 1):
        print(f"  {i}. {option}", flush=True)
    if not sys.stdin.isatty():
        print('기준을 골라 --clarified "..."로 다시 물어보세요', file=sys.stderr)
        return 2
    choice = input("번호 또는 기준> ").strip()
    if not choice:
        return 2
    if choice.isdigit() and 1 <= int(choice) <= len(clarification.options):
        choice = clarification.options[int(choice) - 1]
    return _ask(question, persona, run=run, clarified=choice)


def _run(sql: str, persona: Persona) -> int:
    try:
        rows = execute(sql, persona.user)
    except ExecutionError as e:
        print(f"실행 실패: {e}", file=sys.stderr)
        return 1
    _print_rows(rows)
    return 0


def _print_rows(rows: Rows) -> None:
    print(format_table(rows), flush=True)
    for warning in rows.warnings:
        print(f"주의: {warning}", file=sys.stderr)


def format_table(rows: Rows) -> str:
    cells = [[_cell(v) for v in row] for row in rows.rows]
    widths = [max([_width(c)] + [_width(r[i]) for r in cells]) for i, c in enumerate(rows.columns)]
    lines = [
        " | ".join(_pad(c, w) for c, w in zip(rows.columns, widths)),
        "-+-".join("-" * w for w in widths),
        *(" | ".join(_pad(c, w) for c, w in zip(r, widths)) for r in cells),
    ]
    count = f"({len(rows.rows)}행{', 행 수 제한으로 잘림' if rows.truncated else ''})"
    return "\n".join(lines + [count])


def _cell(value: object) -> str:
    if value is None:
        text = "NULL"
    elif isinstance(value, Decimal):
        text = f"{value:,}"
    elif isinstance(value, datetime):
        text = value.strftime("%Y-%m-%d %H:%M")
    elif isinstance(value, date):
        text = value.isoformat()
    else:
        text = str(value)
    text = text.replace("\n", " ")
    return text if len(text) <= MAX_CELL else text[: MAX_CELL - 1] + "…"


def _width(text: str) -> int:
    # 한글은 터미널에서 두 칸을 차지한다.
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * (width - _width(text))


if __name__ == "__main__":
    sys.exit(main())
