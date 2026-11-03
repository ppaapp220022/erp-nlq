# Odoo shell 안에서 실행한다 (scripts/db-seed.sh). `env`는 shell이 넣어 준다.
# 데모 데이터에 역할별 사용자를 더하고 주문·송장 담당자를 나눈다. 여러 번 실행해도 결과가 같다.
# 역할 정의는 docs/adr/0002-separate-sales-and-stock-roles.md.
# DB를 직접 고치지 않고 ORM으로만 바꾼다.

NEW_SALESPEOPLE = [
    ("sales.kim", "김민준"),
    ("sales.lee", "이서연"),
    ("sales.park", "박지훈"),
]
# 재고 담당. 판매·회계 문서는 보지 않고 재고(와 재고 그룹이 여는 구매)를 회사 범위 전체로 본다.
STOCK_USERS = [
    ("stock.choi", "최윤서"),
]
# 담당자 없는 주문. Odoo 영업 사원 규칙은 담당자 없는 주문도 보여 주므로 검증에 필요하다.
UNASSIGNED_ORDERS = 2

Users = env["res.users"].with_context(no_reset_password=True)
template = env.ref("base.user_demo")  # Marc Demo: 본인 주문만 보는 영업 사원
stock_user = env.ref("stock.group_stock_user")
salesman = env.ref("sales_team.group_sale_salesman")

# 데모의 Marc Demo는 재고 사용자이기도 해서 주문 라인·구매·출고를 전부 본다(그룹 규칙은 OR).
# 영업 사원에서는 재고 그룹을 빼고, 재고는 따로 만든 재고 담당이 맡는다.
sales_groups = template.group_ids - stock_user
stock_groups = (template.group_ids - salesman) | stock_user


def upsert(login, name, groups):
    user = Users.search([("login", "=", login)])
    if not user:
        user = Users.create({"login": login, "name": name})
    # 데모 데이터는 여러 회사에 걸쳐 있다. Odoo 규칙은 사용자가 속한 회사의 문서만 보여 주므로
    # 회사는 Marc Demo와 똑같이 맞춘다.
    user.write({
        "group_ids": [(6, 0, groups.ids)],
        "company_ids": [(6, 0, template.company_ids.ids)],
        "company_id": template.company_id.id,
    })
    return user


template.write({"group_ids": [(6, 0, sales_groups.ids)]})
pool = template
for login, name in NEW_SALESPEOPLE:
    pool |= upsert(login, name, sales_groups)
stock_staff = Users.browse()
for login, name in STOCK_USERS:
    stock_staff |= upsert(login, name, stock_groups)

orders = env["sale.order"].search([], order="id")
orders[:UNASSIGNED_ORDERS].write({"user_id": False})
for i, order in enumerate(orders[UNASSIGNED_ORDERS:]):
    order.user_id = pool[i % len(pool)]

# 이미 담당자가 없는 송장은 그대로 두고, 나머지만 나눈다.
invoices = env["account.move"].search(
    [("move_type", "in", ("out_invoice", "out_refund"))], order="id"
)
assigned = invoices.filtered("invoice_user_id")
for i, move in enumerate(assigned):
    move.invoice_user_id = pool[i % len(pool)]

env.cr.commit()

# 확인: ORM이 사용자 권한으로 보여 주는 수와, Odoo 규칙을 SQL로 옮긴 수가 같은지.
# 영업 사원 = (내 문서 또는 담당자 없음) AND 내가 속한 회사. 재고 담당 = 회사 조건만. 송장은 못 본다(None).
OWN = "({col} = %(uid)s OR {col} IS NULL) AND "
CHECKS = [
    ("orders", "sale.order", [], "SELECT count(*) FROM sale_order WHERE {own}company_id IN %(companies)s", "user_id"),
    ("lines", "sale.order.line", [], "SELECT count(*) FROM sale_order_line WHERE {own}company_id IN %(companies)s", "salesman_id"),
    ("invoices", "account.move", [("move_type", "in", ("out_invoice", "out_refund"))],
     "SELECT count(*) FROM account_move WHERE move_type IN ('out_invoice', 'out_refund')"
     " AND {own}company_id IN %(companies)s", "invoice_user_id"),
]


def orm_count(user, model, domain):
    if not env["ir.model.access"].with_user(user).check(model, "read", raise_exception=False):
        return None
    return env[model].with_user(user).search_count(domain)


def sql_count(user, sql, own_col, role):
    if role == "stock" and own_col == "invoice_user_id":
        return None
    own = OWN.format(col=own_col) if role == "sales" else ""
    env.cr.execute(sql.format(own=own), {"uid": user.id, "companies": tuple(user.company_ids.ids)})
    return env.cr.fetchone()[0]


print(f"{'user':<12}" + "".join(f"{name + ' orm':>14}{name + ' sql':>14}" for name, *_ in CHECKS))
for role, users in (("sales", pool), ("stock", stock_staff)):
    for user in users:
        cells = []
        for _, model, domain, sql, own_col in CHECKS:
            cells += [orm_count(user, model, domain), sql_count(user, sql, own_col, role)]
        print(f"{user.login:<12}" + "".join(f"{'-' if c is None else c:>14}" for c in cells))
