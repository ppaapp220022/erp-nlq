"""사용자 → 테이블별 행 범위. Odoo Record Rule을 옮긴 것이다.

Odoo는 `전역 규칙 AND (사용자 그룹에 걸린 그룹 규칙 OR ...)`로 합친다. 사용자의 어느 그룹에도 그 테이블의
그룹 규칙이 없으면 전역 규칙만 걸린다(docs/reference/odoo-access-rules.md, ADR 0002).
규칙 원문은 `./scripts/odoo-shell.sh scripts/odoo_access_report.py`로 볼 수 있다. 규칙을 바꾸면
backend/tests/test_odoo_scope.py가 Odoo ORM이 센 행 수와 비교한다.

조건은 guard가 `(SELECT ... FROM <테이블> WHERE <조건>) AS <별칭>`으로 끼운다. 열은 테이블 이름을 붙여 쓴다.
`{uid}`와 `{companies}`에는 정수만 들어간다. 같은 조건을 RLS 정책으로도 옮긴다(nlq/rls.py, M6 비교).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nlq.models import User

SALESMAN = "sales_team.group_sale_salesman"
ALL_LEADS = "sales_team.group_sale_salesman_all_leads"
STOCK_USER = "stock.group_stock_user"
PURCHASE_USER = "purchase.group_purchase_user"
INVOICING = "account.group_account_invoice"
ACCOUNT_READONLY = "account.group_account_readonly"
INTERNAL = "base.group_user"
ERP_MANAGER = "base.group_erp_manager"

ALL = "TRUE"  # 그룹 규칙 (1, '=', 1)

# Odoo `company_id parent_of company_ids`: 사용자 회사 자신이거나 그 상위 회사. {parent_companies}는
# 그 id 목록을 내는 쿼리다. guard는 res_company를 직접 읽고, RLS는 res_company 정책을 거치지 않는 함수로 읽는다.
PARENT_COMPANIES = (
    "SELECT a.id FROM res_company a JOIN res_company c ON c.parent_path LIKE a.parent_path || '%'"
    " WHERE c.id IN ({companies})"
)
PARENT_OF = "{col} IN ({parent_companies})"
PARTNER = (
    "(res_partner.partner_share = false OR "
    + PARENT_OF.format(col="res_partner.company_id", parent_companies="{parent_companies}")
    + " OR res_partner.company_id IS NULL)"
)
TEMPLATE = (
    "(" + PARENT_OF.format(col="product_template.company_id", parent_companies="{parent_companies}")
    + " OR product_template.company_id IS NULL)"
)


@dataclass(frozen=True)
class Rule:
    """테이블 하나의 읽기 규칙. group_rules는 (Odoo 그룹, 조건) 목록이고 OR로 합친다."""

    global_rule: str
    group_rules: list[tuple[str, str]] = field(default_factory=list)
    # nlq_readonly가 일부 열만 읽는 테이블. 서브쿼리에서 SELECT * 대신 이 열을 쓴다.
    columns: tuple[str, ...] | None = None


COMPANY = "{table}.company_id IN ({companies})"
COMPANY_OR_NONE = "({table}.company_id IN ({companies}) OR {table}.company_id IS NULL)"

TABLES: dict[str, Rule] = {
    # sale.sale_order_comp_rule, sale_order_personal_rule, sale_order_see_all
    "sale_order": Rule(COMPANY, [
        (SALESMAN, "(sale_order.user_id = {uid} OR sale_order.user_id IS NULL)"),
        (ALL_LEADS, ALL),
    ]),
    # sale.sale_order_line_comp_rule, sale_order_line_personal_rule, sale_order_line_see_all,
    # sale_stock.sale_order_line_rule_stock_user
    "sale_order_line": Rule(COMPANY, [
        (SALESMAN, "(sale_order_line.salesman_id = {uid} OR sale_order_line.salesman_id IS NULL)"),
        (ALL_LEADS, ALL),
        (STOCK_USER, ALL),
    ]),
    "purchase_order": Rule(COMPANY),  # purchase.purchase_order_comp_rule
    "purchase_order_line": Rule(COMPANY),  # purchase.purchase_order_line_comp_rule
    "stock_picking": Rule(COMPANY),  # stock.stock_picking_rule
    "stock_warehouse_orderpoint": Rule(COMPANY),  # stock.stock_warehouse_orderpoint_rule
    "stock_quant": Rule(COMPANY_OR_NONE),  # stock.stock_quant_rule
    "stock_location": Rule(COMPANY_OR_NONE),  # stock.stock_location_comp_rule
    # account.account_move_comp_rule, account_move_see_all, account_move_rule_group_invoice,
    # account_move_rule_group_readonly, purchase.purchase_user_account_move_rule,
    # sale.account_invoice_rule_see_personal, sale.account_invoice_rule_see_all
    "account_move": Rule(COMPANY, [
        (INVOICING, ALL),
        (ACCOUNT_READONLY, ALL),
        (PURCHASE_USER, "account_move.move_type IN ('in_invoice', 'in_refund', 'in_receipt')"),
        (SALESMAN, "(account_move.move_type IN ('out_invoice', 'out_refund')"
                   " AND (account_move.invoice_user_id = {uid} OR account_move.invoice_user_id IS NULL))"),
        (ALL_LEADS, "account_move.move_type IN ('out_invoice', 'out_refund')"),
    ]),
    "res_partner": Rule(PARTNER),  # base.res_partner_rule
    # base.res_company_rule_employee, res_company_rule_erp_manager. 전역 규칙이 없다
    "res_company": Rule(ALL, [
        (INTERNAL, "res_company.id IN ({companies})"),
        (ERP_MANAGER, ALL),
    ]),
    "product_template": Rule(TEMPLATE),  # product.product_comp_rule
    # product.product은 규칙이 없고 템플릿의 규칙을 따른다(_inherits)
    "product_product": Rule(
        "product_product.product_tmpl_id IN (SELECT product_template.id FROM product_template WHERE " + TEMPLATE + ")"
    ),
    # base.res_users_rule: 보이는 파트너 AND (내부 사용자 OR company_ids가 겹침).
    # company_ids(다대다)는 열려 있지 않아 company_id로 좁힌다. 현재 회사는 항상 company_ids 안에 있으므로
    # Odoo보다 넓어지지 않는다.
    "res_users": Rule(
        "res_users.partner_id IN (SELECT res_partner.id FROM res_partner WHERE " + PARTNER + ")"
        " AND (res_users.share = false OR res_users.company_id IN ({companies}))",
        columns=("id", "partner_id", "company_id", "active", "share"),
    ),
}


def can_read(table: str, user: User) -> bool:
    """Odoo가 읽기 권한(ACL)을 주고, 행 범위 규칙도 옮겨 둔 테이블만 읽는다."""
    return table in TABLES and table in user.tables


def row_scope(table: str, user: User) -> str:
    """테이블의 행 범위 조건. can_read가 참일 때만 부른다."""
    rule = TABLES[table]
    matched = [cond for group, cond in rule.group_rules if group in user.groups]
    parts = [rule.global_rule]
    if matched and ALL not in matched:
        parts.append("(" + " OR ".join(matched) + ")")
    companies = ", ".join(str(int(c)) for c in user.company_ids) or "NULL"
    return " AND ".join(parts).format(
        table=table,
        uid=int(user.odoo_uid),
        companies=companies,
        parent_companies=PARENT_COMPANIES.format(companies=companies),
    )
