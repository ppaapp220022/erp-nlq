# Odoo shell 안에서 실행한다: ./scripts/odoo-shell.sh scripts/odoo_access_report.py
# 허용 테이블 후보 모델마다 (1) 읽기 Record Rule 원문, (2) 사용자별 접근 권한·최종 도메인·보이는 건수를 출력한다.
# docs/reference/odoo-access-rules.md의 근거 데이터다. Odoo나 데이터를 바꾸면 다시 돌려 문서와 비교한다.

MODELS = [
    "sale.order", "sale.order.line",
    "purchase.order", "purchase.order.line",
    "stock.picking", "stock.quant", "stock.location", "stock.warehouse.orderpoint",
    "account.move",
    "res.partner", "res.company", "product.product", "product.template", "res.users",
]
USERS = ["sales.kim", "admin"]
GROUPS = [
    "sales_team.group_sale_salesman", "sales_team.group_sale_salesman_all_leads",
    "sales_team.group_sale_manager", "stock.group_stock_user",
    "purchase.group_purchase_user", "account.group_account_invoice",
]


def xid(record):
    return record.get_external_id().get(record.id) or record.display_name


print("## Record Rules (read)")
for model in MODELS:
    rules = env["ir.rule"].sudo().search(
        [("model_id.model", "=", model), ("active", "=", True), ("perm_read", "=", True)]
    )
    for rule in rules:
        groups = ",".join(xid(g) for g in rule.groups) or "GLOBAL"
        if groups in ("base.group_portal", "base.group_portal,base.group_public", "base.group_public"):
            continue  # 포털·공개 사용자는 이 프로젝트의 역할이 아니다
        print(f"{model} | {xid(rule)} | {groups} | {rule.domain_force.strip()}")

for login in USERS:
    user = env["res.users"].search([("login", "=", login)])
    print(f"\n## {login}: {[g for g in GROUPS if user.has_group(g)]}")
    for model in MODELS:
        readable = env["ir.model.access"].with_user(user).check(model, "read", raise_exception=False)
        if not readable:
            print(f"{model} | read=False")
            continue
        domain = env["ir.rule"].with_user(user)._compute_domain(model, "read")
        count = env[model].with_user(user).search_count([])
        print(f"{model} | visible={count} | {domain}")
