# Odoo shell 안에서 실행한다: ./scripts/odoo-shell.sh scripts/odoo_report_totals.py > eval/odoo_reports.toml
# 사용자마다 Odoo 보고서가 보여 주는 매출·수주액·미수금·연체 미수금을 회사별로 출력한다.
# 질의 시스템의 답을 Odoo 보고서와 대조하는 기준이다(backend/nlq/report_check.py, docs/plan.md "Odoo 보고서 대조").
# 각 사용자의 권한(with_user)과 그 사용자가 속한 회사 전체로 집계하므로, 권한 범위까지 함께 대조된다.
# 지표 정의는 knowledge/metrics/ 와 같다. today는 eval/config.yaml의 값이다.

TODAY = "2026-11-03"
MONTH = ("2026-11-01", "2026-12-01")
CUSTOMER = ("out_invoice", "out_refund")

METRICS = {
    # 이름: (모델, 도메인, 합계 필드). 근거는 knowledge/metrics/revenue.md, receivable.md
    "revenue": ("account.invoice.report", [("move_type", "in", CUSTOMER), ("state", "=", "posted")], "price_subtotal"),
    "revenue_this_month": (
        "account.invoice.report",
        [("move_type", "in", CUSTOMER), ("state", "=", "posted"), ("invoice_date", ">=", MONTH[0]), ("invoice_date", "<", MONTH[1])],
        "price_subtotal",
    ),
    "order_amount": ("sale.report", [("state", "=", "sale")], "price_subtotal"),
    "receivable": (
        "account.move",
        [("move_type", "in", CUSTOMER), ("state", "=", "posted"), ("payment_state", "in", ("not_paid", "partial"))],
        "amount_residual_signed",
    ),
    "overdue_receivable": (
        "account.move",
        [("move_type", "in", CUSTOMER), ("state", "=", "posted"), ("payment_state", "in", ("not_paid", "partial")),
         ("invoice_date_due", "<", TODAY)],
        "amount_residual_signed",
    ),
}

print("# scripts/odoo_report_totals.py 로 생성. 직접 고치지 않는다. 읽기 권한이 없는 보고서와 값이 없는 회사는 빠진다.")
print(f'today = "{TODAY}"')
for user in env["res.users"].search([("share", "=", False), ("login", "!=", "__system__")], order="id"):
    access = env["ir.model.access"].with_user(user)
    out = {}
    for name, (model, domain, field) in METRICS.items():
        if not access.check(model, "read", raise_exception=False):
            continue
        records = env[model].with_user(user).with_context(allowed_company_ids=user.company_ids.ids)
        groups = records._read_group(domain, groupby=["company_id"], aggregates=[f"{field}:sum"])
        out[name] = {company.name: round(total, 2) for company, total in groups if company}
    if not any(out.values()):
        continue
    for name, by_company in out.items():
        if by_company:
            print(f'\n[reports."{user.login}".{name}]')
            for company, total in sorted(by_company.items()):
                print(f'"{company}" = {total:.2f}')
