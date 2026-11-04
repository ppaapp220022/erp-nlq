# Odoo shell 안에서 실행한다: ./scripts/odoo-shell.sh scripts/odoo_users.py > eval/users.toml
# 질의 계층이 쓰는 사용자 목록(id, 소속 회사, 역할)을 TOML로 출력한다. `env`는 shell이 넣어 준다.
# nlq_readonly는 로그인 이름과 소속 회사를 읽을 수 없어서 이 파일로 넘긴다. 스냅숏을 바꾸면 다시 뽑는다.

ROLES = [  # 위에서부터 먼저 맞는 것. 역할 정의는 docs/adr/0002-separate-sales-and-stock-roles.md
    ("base.group_system", "관리자"),
    ("sales_team.group_sale_salesman_all_leads", "영업 관리자"),
    ("sales_team.group_sale_salesman", "영업 사원"),
    ("stock.group_stock_user", "재고 담당"),
]

print("# scripts/odoo_users.py 로 생성. 직접 고치지 않는다.")
for user in env["res.users"].search([("share", "=", False)], order="id"):
    role = next((name for xid, name in ROLES if user.has_group(xid)), None)
    if role is None:
        continue
    print(f'\n[users."{user.login}"]')
    print(f"uid = {user.id}")
    print(f'role = "{role}"')
    print(f"companies = {sorted(user.company_ids.ids)}")
