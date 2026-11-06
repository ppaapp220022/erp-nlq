-- 질의 계층이 쓰는 읽기 전용 역할.
-- scripts/db-readonly-role.sh 가 psql 변수 ro_user, ro_password, db_name 을 넘겨 실행한다.
-- 여러 번 실행해도 같은 결과가 되도록, 테이블 권한은 매번 전부 회수한 뒤 다시 준다.

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I LOGIN', :'ro_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'ro_user') \gexec

ALTER ROLE :"ro_user" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS
  PASSWORD :'ro_password';
-- 쓰기 SQL을 트랜잭션 단계에서 한 번 더 막는다. 세션에서 끌 수 있는 설정이라
-- 실제 방어선은 아래 SELECT 권한이다.
ALTER ROLE :"ro_user" SET default_transaction_read_only = on;

GRANT CONNECT ON DATABASE :"db_name" TO :"ro_user";
GRANT USAGE ON SCHEMA public TO :"ro_user";

-- Odoo가 만든 DB는 PUBLIC에 public 스키마 CREATE와 임시 테이블 권한이 열려 있다.
-- 특정 역할만 막을 수 없어 PUBLIC에서 회수한다. 소유자(odoo)는 영향이 없다.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE TEMPORARY ON DATABASE :"db_name" FROM PUBLIC;

BEGIN;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM :"ro_user";

-- 허용 테이블 (M1 확정, 13개 + res_users 일부 열). 고른 이유는 docs/reference/odoo-access-rules.md.
-- 역할별로 더 좁히는 것은 guard가 한다. 여기는 질의 계층 전체가 읽을 수 있는 상한이다.
-- 판매
GRANT SELECT ON sale_order, sale_order_line TO :"ro_user";
-- 구매
GRANT SELECT ON purchase_order, purchase_order_line TO :"ro_user";
-- 재고. stock_quant는 창고 밖 위치에도 있어서 stock_location.usage로 걸러야 한다.
GRANT SELECT ON stock_picking, stock_quant, stock_location, stock_warehouse_orderpoint TO :"ro_user";
-- 회계. 송장 단위만 연다. 라인(account_move_line)은 평가 문항에 필요해지면 연다.
GRANT SELECT ON account_move TO :"ro_user";
-- 공통 마스터
GRANT SELECT ON res_partner, res_company, product_product, product_template TO :"ro_user";
-- 담당 영업 사원 연결용. 비밀번호 등 나머지 열은 주지 않는다.
-- share(포털 사용자 여부)는 guard가 Odoo res_users 규칙을 옮기는 데 쓴다.
GRANT SELECT (id, partner_id, company_id, active, share) ON res_users TO :"ro_user";

COMMIT;
