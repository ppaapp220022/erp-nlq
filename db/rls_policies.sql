-- 생성 파일. 직접 고치지 않는다: uv run --directory backend python -m nlq.rls > db/rls_policies.sql
-- 규칙은 backend/nlq/identity.py, 사용자 문맥 함수는 db/rls_context.sql 에 있다.
-- scripts/db-readonly-role.sh 가 psql 변수 ro_user, rls_user 를 넘겨 실행한다.
--
-- RLS를 켜면 정책이 없는 역할은 행을 하나도 못 읽는다. 그래서 두 역할에 정책을 따로 둔다.
--   ro_user (nlq_readonly): guard가 SQL을 재작성해 범위를 거는 경로. 정책은 모든 행을 연다.
--   rls_user (nlq_rls):      guard 재작성 없이 정책이 범위를 거는 경로 (ADR 0005).
-- FORCE ROW LEVEL SECURITY는 쓰지 않는다. 소유자이자 superuser인 odoo(Odoo 서버)는 영향이 없다.

\set ON_ERROR_STOP on
SET client_min_messages = warning;

BEGIN;

-- account_move
ALTER TABLE account_move ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON account_move;
CREATE POLICY nlq_guard ON account_move FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON account_move;
CREATE POLICY nlq_rls ON account_move FOR SELECT TO :"rls_user"
  USING (nlq.can_read('account_move') AND account_move.company_id IN (SELECT unnest(nlq.company_ids())) AND (NOT (nlq.has_group('account.group_account_invoice') OR nlq.has_group('account.group_account_readonly') OR nlq.has_group('purchase.group_purchase_user') OR nlq.has_group('sales_team.group_sale_salesman') OR nlq.has_group('sales_team.group_sale_salesman_all_leads')) OR (nlq.has_group('account.group_account_invoice') AND TRUE) OR (nlq.has_group('account.group_account_readonly') AND TRUE) OR (nlq.has_group('purchase.group_purchase_user') AND account_move.move_type IN ('in_invoice', 'in_refund', 'in_receipt')) OR (nlq.has_group('sales_team.group_sale_salesman') AND (account_move.move_type IN ('out_invoice', 'out_refund') AND (account_move.invoice_user_id = nlq.uid() OR account_move.invoice_user_id IS NULL))) OR (nlq.has_group('sales_team.group_sale_salesman_all_leads') AND account_move.move_type IN ('out_invoice', 'out_refund'))));

-- product_product
ALTER TABLE product_product ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON product_product;
CREATE POLICY nlq_guard ON product_product FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON product_product;
CREATE POLICY nlq_rls ON product_product FOR SELECT TO :"rls_user"
  USING (nlq.can_read('product_product') AND product_product.product_tmpl_id IN (SELECT product_template.id FROM product_template WHERE (product_template.company_id IN (SELECT unnest(nlq.parent_company_ids())) OR product_template.company_id IS NULL)));

-- product_template
ALTER TABLE product_template ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON product_template;
CREATE POLICY nlq_guard ON product_template FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON product_template;
CREATE POLICY nlq_rls ON product_template FOR SELECT TO :"rls_user"
  USING (nlq.can_read('product_template') AND (product_template.company_id IN (SELECT unnest(nlq.parent_company_ids())) OR product_template.company_id IS NULL));

-- purchase_order
ALTER TABLE purchase_order ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON purchase_order;
CREATE POLICY nlq_guard ON purchase_order FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON purchase_order;
CREATE POLICY nlq_rls ON purchase_order FOR SELECT TO :"rls_user"
  USING (nlq.can_read('purchase_order') AND purchase_order.company_id IN (SELECT unnest(nlq.company_ids())));

-- purchase_order_line
ALTER TABLE purchase_order_line ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON purchase_order_line;
CREATE POLICY nlq_guard ON purchase_order_line FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON purchase_order_line;
CREATE POLICY nlq_rls ON purchase_order_line FOR SELECT TO :"rls_user"
  USING (nlq.can_read('purchase_order_line') AND purchase_order_line.company_id IN (SELECT unnest(nlq.company_ids())));

-- res_company
ALTER TABLE res_company ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON res_company;
CREATE POLICY nlq_guard ON res_company FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON res_company;
CREATE POLICY nlq_rls ON res_company FOR SELECT TO :"rls_user"
  USING (nlq.can_read('res_company') AND TRUE AND (NOT (nlq.has_group('base.group_user') OR nlq.has_group('base.group_erp_manager')) OR (nlq.has_group('base.group_user') AND res_company.id IN (SELECT unnest(nlq.company_ids()))) OR (nlq.has_group('base.group_erp_manager') AND TRUE)));

-- res_partner
ALTER TABLE res_partner ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON res_partner;
CREATE POLICY nlq_guard ON res_partner FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON res_partner;
CREATE POLICY nlq_rls ON res_partner FOR SELECT TO :"rls_user"
  USING (nlq.can_read('res_partner') AND (res_partner.partner_share = false OR res_partner.company_id IN (SELECT unnest(nlq.parent_company_ids())) OR res_partner.company_id IS NULL));

-- res_users
ALTER TABLE res_users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON res_users;
CREATE POLICY nlq_guard ON res_users FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON res_users;
CREATE POLICY nlq_rls ON res_users FOR SELECT TO :"rls_user"
  USING (nlq.can_read('res_users') AND res_users.partner_id IN (SELECT res_partner.id FROM res_partner WHERE (res_partner.partner_share = false OR res_partner.company_id IN (SELECT unnest(nlq.parent_company_ids())) OR res_partner.company_id IS NULL)) AND (res_users.share = false OR res_users.company_id IN (SELECT unnest(nlq.company_ids()))));

-- sale_order
ALTER TABLE sale_order ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON sale_order;
CREATE POLICY nlq_guard ON sale_order FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON sale_order;
CREATE POLICY nlq_rls ON sale_order FOR SELECT TO :"rls_user"
  USING (nlq.can_read('sale_order') AND sale_order.company_id IN (SELECT unnest(nlq.company_ids())) AND (NOT (nlq.has_group('sales_team.group_sale_salesman') OR nlq.has_group('sales_team.group_sale_salesman_all_leads')) OR (nlq.has_group('sales_team.group_sale_salesman') AND (sale_order.user_id = nlq.uid() OR sale_order.user_id IS NULL)) OR (nlq.has_group('sales_team.group_sale_salesman_all_leads') AND TRUE)));

-- sale_order_line
ALTER TABLE sale_order_line ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON sale_order_line;
CREATE POLICY nlq_guard ON sale_order_line FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON sale_order_line;
CREATE POLICY nlq_rls ON sale_order_line FOR SELECT TO :"rls_user"
  USING (nlq.can_read('sale_order_line') AND sale_order_line.company_id IN (SELECT unnest(nlq.company_ids())) AND (NOT (nlq.has_group('sales_team.group_sale_salesman') OR nlq.has_group('sales_team.group_sale_salesman_all_leads') OR nlq.has_group('stock.group_stock_user')) OR (nlq.has_group('sales_team.group_sale_salesman') AND (sale_order_line.salesman_id = nlq.uid() OR sale_order_line.salesman_id IS NULL)) OR (nlq.has_group('sales_team.group_sale_salesman_all_leads') AND TRUE) OR (nlq.has_group('stock.group_stock_user') AND TRUE)));

-- stock_location
ALTER TABLE stock_location ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON stock_location;
CREATE POLICY nlq_guard ON stock_location FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON stock_location;
CREATE POLICY nlq_rls ON stock_location FOR SELECT TO :"rls_user"
  USING (nlq.can_read('stock_location') AND (stock_location.company_id IN (SELECT unnest(nlq.company_ids())) OR stock_location.company_id IS NULL));

-- stock_picking
ALTER TABLE stock_picking ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON stock_picking;
CREATE POLICY nlq_guard ON stock_picking FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON stock_picking;
CREATE POLICY nlq_rls ON stock_picking FOR SELECT TO :"rls_user"
  USING (nlq.can_read('stock_picking') AND stock_picking.company_id IN (SELECT unnest(nlq.company_ids())));

-- stock_quant
ALTER TABLE stock_quant ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON stock_quant;
CREATE POLICY nlq_guard ON stock_quant FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON stock_quant;
CREATE POLICY nlq_rls ON stock_quant FOR SELECT TO :"rls_user"
  USING (nlq.can_read('stock_quant') AND (stock_quant.company_id IN (SELECT unnest(nlq.company_ids())) OR stock_quant.company_id IS NULL));

-- stock_warehouse_orderpoint
ALTER TABLE stock_warehouse_orderpoint ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS nlq_guard ON stock_warehouse_orderpoint;
CREATE POLICY nlq_guard ON stock_warehouse_orderpoint FOR SELECT TO :"ro_user" USING (true);
DROP POLICY IF EXISTS nlq_rls ON stock_warehouse_orderpoint;
CREATE POLICY nlq_rls ON stock_warehouse_orderpoint FOR SELECT TO :"rls_user"
  USING (nlq.can_read('stock_warehouse_orderpoint') AND stock_warehouse_orderpoint.company_id IN (SELECT unnest(nlq.company_ids())));

COMMIT;
