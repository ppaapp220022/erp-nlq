"""질의 시스템의 답을 Odoo 보고서와 대조한다 (M5 "Odoo 보고서 대조").

    uv run --directory backend nlq-report              # 정의 SQL과 시스템 답(Claude API) 둘 다
    uv run --directory backend nlq-report --no-ask     # 정의 SQL만 (API를 부르지 않는다)

Odoo 쪽 숫자는 scripts/odoo_report_totals.py가 Odoo ORM으로 사용자마다(with_user) 뽑아 eval/odoo_reports.toml에 둔다.
대조는 두 가지다.
  정의 SQL   knowledge/metrics/의 정의를 그 사용자로 execute()한 결과. 권한 범위가 합계 수준에서도 Odoo와 같은지 본다
  시스템 답  같은 지표를 묻는 한국어 질문을 ask()로 돌린 결과. 채점 규칙은 평가와 같다(nlq/scoring.py)
DB와 API로 가는 길은 execute()와 ask()(generate + execute)뿐이다.
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from dataclasses import dataclass
from decimal import Decimal

from nlq import GenerationError, execute
from nlq.ask import ask
from nlq.generate import DEFAULT_MODEL
from nlq.models import GuardError, Rows
from nlq.scoring import matches, normalize
from nlq.settings import ROOT, setting
from nlq.users import load_users

ODOO_REPORTS = ROOT / "eval" / "odoo_reports.toml"

_CUSTOMER = "m.state = 'posted' AND m.move_type IN ('out_invoice', 'out_refund')"
_BY_COMPANY = "FROM account_move m JOIN res_company c ON c.id = m.company_id WHERE " + _CUSTOMER


@dataclass(frozen=True)
class Metric:
    question: str
    sql: str


# 정의는 knowledge/metrics/revenue.md, receivable.md와 같다. 회사별로 낸다.
METRICS: dict[str, Metric] = {
    "revenue": Metric(
        "회사별 매출",
        f"SELECT c.name, sum(m.amount_untaxed_signed) {_BY_COMPANY} GROUP BY c.name",
    ),
    "revenue_this_month": Metric(
        "회사별 이번 달 매출",
        f"SELECT c.name, sum(m.amount_untaxed_signed) {_BY_COMPANY}"
        " AND m.invoice_date >= '2026-11-01' AND m.invoice_date < '2026-12-01' GROUP BY c.name",
    ),
    "order_amount": Metric(
        "회사별 수주액 (확정 주문, 부가세 제외)",
        "SELECT c.name, sum(l.price_subtotal) FROM sale_order_line l"
        " JOIN sale_order o ON o.id = l.order_id JOIN res_company c ON c.id = o.company_id"
        " WHERE o.state = 'sale' AND l.display_type IS NULL GROUP BY c.name",
    ),
    "receivable": Metric(
        "회사별 미수금",
        f"SELECT c.name, sum(m.amount_residual_signed) {_BY_COMPANY} GROUP BY c.name",
    ),
    "overdue_receivable": Metric(
        "회사별 연체 미수금",
        f"SELECT c.name, sum(m.amount_residual_signed) {_BY_COMPANY} AND m.invoice_date_due < '2026-11-03' GROUP BY c.name",
    ),
}


@dataclass
class Check:
    login: str
    metric: str
    odoo: dict[str, Decimal]
    definition: dict[str, Decimal] | None = None
    # correct | wrong | clarification | generation_error | guard_rejected | execution_error | skipped
    answer: str = "skipped"
    answer_sql: str | None = None


def load_odoo_reports() -> dict[str, dict[str, dict[str, Decimal]]]:
    data = tomllib.loads(ODOO_REPORTS.read_text())
    return {
        login: {metric: {c: Decimal(str(v)) for c, v in by_company.items()} for metric, by_company in metrics.items()}
        for login, metrics in data["reports"].items()
    }


def by_company(rows: Rows) -> dict[str, Decimal]:
    # Odoo는 합계가 0인 회사도 행을 내지만, 레코드가 없는 회사는 내지 않는다. 정의 SQL도 같다.
    return {name: normalize(total) for name, total in rows.rows if total is not None}


def odoo_rows(totals: dict[str, Decimal]) -> Rows:
    return Rows(columns=["company", "amount"], rows=sorted(totals.items()), executed_sql="")


def check_definition(login: str, metric: str, odoo: dict[str, Decimal]) -> Check:
    user = load_users()[login].user
    result = Check(login=login, metric=metric, odoo={c: normalize(v) for c, v in odoo.items()})
    result.definition = by_company(execute(METRICS[metric].sql, user))
    return result


def check_answer(check: Check) -> Check:
    user = load_users()[check.login].user
    try:
        last = ask(METRICS[check.metric].question, user)[-1]
    except GenerationError:
        check.answer = "generation_error"
        return check
    check.answer_sql = last.sql or None
    if last.clarification is not None:
        check.answer = "clarification"
    elif last.error is not None:
        check.answer = "guard_rejected" if isinstance(last.error, GuardError) else "execution_error"
    else:
        check.answer = "correct" if matches(odoo_rows(check.odoo), last.rows, order_matters=False) else "wrong"
    return check


def run(ask_system: bool = True) -> list[Check]:
    checks = []
    for login, metrics in load_odoo_reports().items():
        for metric, odoo in metrics.items():
            check = check_definition(login, metric, odoo)
            checks.append(check_answer(check) if ask_system else check)
    return checks


def format_checks(checks: list[Check]) -> str:
    lines = ["| 사용자 | 지표 | Odoo | 정의 SQL | 시스템 답 |", "|---|---|---|---|---|"]
    for c in checks:
        odoo = ", ".join(f"{k} {v:,}" for k, v in sorted(c.odoo.items()))
        definition = "일치" if c.definition == c.odoo else f"다름: {c.definition}"
        lines.append(f"| {c.login} | {c.metric} | {odoo} | {definition} | {c.answer} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nlq-report", description="Odoo 보고서 대조")
    parser.add_argument("--model", help=f"Claude 모델 ID (기본: EVAL_MODEL, 없으면 {DEFAULT_MODEL})")
    parser.add_argument("--no-ask", action="store_true", help="정의 SQL만 대조한다 (Claude API를 부르지 않는다)")
    args = parser.parse_args(argv)
    if args.model:
        os.environ["EVAL_MODEL"] = args.model
    if not args.no_ask:
        print(f"모델 {setting('EVAL_MODEL', DEFAULT_MODEL)}", file=sys.stderr)
    checks = run(ask_system=not args.no_ask)
    print(format_checks(checks))
    defined = sum(c.definition == c.odoo for c in checks)
    print(f"\n정의 SQL 일치 {defined}/{len(checks)}", file=sys.stderr)
    if not args.no_ask:
        print(f"시스템 답 일치 {sum(c.answer == 'correct' for c in checks)}/{len(checks)}", file=sys.stderr)
    return 0 if defined == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
