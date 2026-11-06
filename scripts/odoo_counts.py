# Odoo shell 안에서 실행한다: ./scripts/odoo-shell.sh scripts/odoo_counts.py > backend/tests/odoo_counts.toml
# 사용자마다 허용 테이블별로 Odoo가 보여 주는 행 수를 출력한다. guard의 행 범위가 Odoo와 같은지 비교하는 기준이다
# (backend/tests/test_odoo_scope.py). 보관(active=False)은 권한이 아니라 화면 필터라서 포함해 센다.
# 회사는 사용자가 속한 회사 전체를 고른 상태다(docs/architecture.md "신원과 역할").

MODELS = [
    "sale.order", "sale.order.line",
    "purchase.order", "purchase.order.line",
    "stock.picking", "stock.quant", "stock.location", "stock.warehouse.orderpoint",
    "account.move",
    "res.partner", "res.company", "product.product", "product.template", "res.users",
]

print("# scripts/odoo_counts.py 로 생성. 직접 고치지 않는다. 읽기 권한이 없는 테이블은 빠진다.")
for user in env["res.users"].search([("share", "=", False), ("login", "!=", "__system__")], order="id"):
    access = env["ir.model.access"].with_user(user)
    counts = {}
    for model in MODELS:
        if not access.check(model, "read", raise_exception=False):
            continue
        records = env[model].with_user(user).with_context(active_test=False, allowed_company_ids=user.company_ids.ids)
        counts[model.replace(".", "_")] = records.search_count([])
    if not counts:
        continue
    print(f'\n[counts."{user.login}"]')
    for table, n in counts.items():
        print(f"{table} = {n}")
