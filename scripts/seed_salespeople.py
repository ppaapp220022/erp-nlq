# Odoo shell 안에서 실행한다 (scripts/db-seed.sh). `env`는 shell이 넣어 준다.
# 데모 데이터에 영업 사원을 더하고 주문·송장 담당자를 나눈다. 여러 번 실행해도 결과가 같다.
# DB를 직접 고치지 않고 ORM으로만 바꾼다.

NEW_SALESPEOPLE = [
    ("sales.kim", "김민준"),
    ("sales.lee", "이서연"),
    ("sales.park", "박지훈"),
]
# 담당자 없는 주문. Odoo 영업 사원 규칙은 담당자 없는 주문도 보여 주므로 검증에 필요하다.
UNASSIGNED_ORDERS = 2

Users = env["res.users"].with_context(no_reset_password=True)
template = env.ref("base.user_demo")  # Marc Demo: 본인 주문만 보는 영업 사원

pool = template
for login, name in NEW_SALESPEOPLE:
    user = Users.search([("login", "=", login)])
    if not user:
        user = Users.create({"login": login, "name": name})
    # 데모 데이터는 여러 회사에 걸쳐 있다. Odoo 규칙은 사용자가 속한 회사의 문서만 보여 주므로
    # 그룹과 회사를 Marc Demo와 똑같이 맞춘다.
    user.write({
        "group_ids": [(6, 0, template.group_ids.ids)],
        "company_ids": [(6, 0, template.company_ids.ids)],
        "company_id": template.company_id.id,
    })
    pool |= user

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
# 규칙 = (내 문서 또는 담당자 없음) AND 내가 속한 회사.
print(f"{'user':<12}{'orders orm':>12}{'orders sql':>12}{'inv orm':>10}{'inv sql':>10}")
for user in pool:
    companies = tuple(user.company_ids.ids)
    orm_orders = env["sale.order"].with_user(user).search_count([])
    env.cr.execute(
        "SELECT count(*) FROM sale_order"
        " WHERE (user_id = %s OR user_id IS NULL) AND company_id IN %s",
        [user.id, companies],
    )
    sql_orders = env.cr.fetchone()[0]
    orm_inv = env["account.move"].with_user(user).search_count(
        [("move_type", "in", ("out_invoice", "out_refund"))]
    )
    env.cr.execute(
        "SELECT count(*) FROM account_move WHERE move_type IN ('out_invoice', 'out_refund')"
        " AND (invoice_user_id = %s OR invoice_user_id IS NULL) AND company_id IN %s",
        [user.id, companies],
    )
    sql_inv = env.cr.fetchone()[0]
    print(f"{user.login:<12}{orm_orders:>12}{sql_orders:>12}{orm_inv:>10}{sql_inv:>10}")
