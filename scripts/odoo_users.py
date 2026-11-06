# Odoo shell 안에서 실행한다: ./scripts/odoo-shell.sh scripts/odoo_users.py > eval/users.toml
# 질의 계층이 쓰는 사용자 목록(id, 소속 회사, 역할, 권한 그룹, 읽을 수 있는 테이블)을 TOML로 출력한다. `env`는 shell이 넣어 준다.
# nlq_readonly는 로그인 이름, 소속 회사, 그룹을 읽을 수 없어서 이 파일로 넘긴다. 스냅숏이나 그룹을 바꾸면 다시 뽑는다.
# 행 범위 규칙 자체는 backend/nlq/identity.py에 있다. 여기서는 사용자가 어느 그룹에 속하는지만 넘긴다.

ROLES = [  # 위에서부터 먼저 맞는 것. 역할 정의는 docs/adr/0002-separate-sales-and-stock-roles.md
    ("base.group_system", "관리자"),
    ("sales_team.group_sale_salesman_all_leads", "영업 관리자"),
    ("sales_team.group_sale_salesman", "영업 사원"),
    ("stock.group_stock_user", "재고 담당"),
]

# 허용 테이블(db/readonly_role.sql)의 모델. 테이블 이름은 점을 밑줄로 바꾼 것이다.
MODELS = [
    "sale.order", "sale.order.line",
    "purchase.order", "purchase.order.line",
    "stock.picking", "stock.quant", "stock.location", "stock.warehouse.orderpoint",
    "account.move",
    "res.partner", "res.company", "product.product", "product.template", "res.users",
]

# 위 모델의 읽기 Record Rule에 걸린 그룹. 사용자 그룹 중 이것만 넘긴다.
rules = env["ir.rule"].sudo().search([("model_id.model", "in", MODELS), ("active", "=", True), ("perm_read", "=", True)])
RULE_GROUPS = {xid for g in rules.groups for xid in [g.get_external_id().get(g.id)] if xid}


def quoted(values):
    return "[" + ", ".join(f'"{v}"' for v in values) + "]"


print("# scripts/odoo_users.py 로 생성. 직접 고치지 않는다.")
for user in env["res.users"].search([("share", "=", False)], order="id"):
    role = next((name for xid, name in ROLES if user.has_group(xid)), None)
    if role is None:
        continue
    groups = sorted(xid for xid in RULE_GROUPS if user.has_group(xid))
    access = env["ir.model.access"].with_user(user)
    tables = sorted(m.replace(".", "_") for m in MODELS if access.check(m, "read", raise_exception=False))
    print(f'\n[users."{user.login}"]')
    print(f"uid = {user.id}")
    print(f'role = "{role}"')
    print(f"companies = {sorted(user.company_ids.ids)}")
    print(f"groups = {quoted(groups)}")
    print(f"tables = {quoted(tables)}")
