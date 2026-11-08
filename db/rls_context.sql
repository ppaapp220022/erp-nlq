-- RLS 정책이 읽는 사용자 문맥 (M6 비교, docs/adr/0005-rls-vs-guard.md).
-- scripts/db-readonly-role.sh 가 psql 변수 rls_user 를 넘겨 실행한다. 정책은 db/rls_policies.sql.
--
-- execute()가 트랜잭션마다 SET LOCAL로 nlq.uid, nlq.company_ids, nlq.groups, nlq.tables 를 넣는다.
-- nlq_rls 는 current_setting·set_config 실행 권한이 없어서(db/readonly_role.sql) 값을 읽거나 바꾸지 못하고,
-- 아래 함수로만 읽는다. 함수는 소유자(odoo) 권한으로 돌며 nlq.* 값만 돌려준다.
-- nlq.uid 가 비어 있으면 모든 함수가 오류를 낸다. 문맥 없이 실행하면 행이 아니라 오류가 나온다(실패 시 닫힘).

\set ON_ERROR_STOP on

BEGIN;

CREATE SCHEMA IF NOT EXISTS nlq;
REVOKE ALL ON SCHEMA nlq FROM PUBLIC;
GRANT USAGE ON SCHEMA nlq TO :"rls_user";

-- 값 하나를 읽는다. nlq.uid 가 없으면 문맥 전체가 없는 것으로 보고 오류를 낸다. 역할에 주지 않는다.
CREATE OR REPLACE FUNCTION nlq._context(name text) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  IF coalesce(current_setting('nlq.uid', true), '') = '' THEN
    RAISE EXCEPTION '권한 문맥(nlq.uid)이 없다';
  END IF;
  RETURN coalesce(current_setting(name, true), '');
END
$$;

CREATE OR REPLACE FUNCTION nlq.uid() RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
  SELECT nlq._context('nlq.uid')::integer
$$;

CREATE OR REPLACE FUNCTION nlq.company_ids() RETURNS integer[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
  SELECT coalesce(string_to_array(nullif(nlq._context('nlq.company_ids'), ''), ',')::integer[], '{}')
$$;

-- Odoo `parent_of company_ids`. res_company 정책을 거치지 않고 읽어야 상위 회사가 빠지지 않는다.
CREATE OR REPLACE FUNCTION nlq.parent_company_ids() RETURNS integer[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
  SELECT coalesce(array_agg(DISTINCT a.id), '{}')
  FROM public.res_company a
  JOIN public.res_company c ON c.parent_path LIKE a.parent_path || '%'
  WHERE c.id = ANY (nlq.company_ids())
$$;

CREATE OR REPLACE FUNCTION nlq.has_group(xmlid text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
  SELECT xmlid = ANY (string_to_array(nlq._context('nlq.groups'), ','))
$$;

-- Odoo ACL(ir.model.access). eval/users.toml 의 tables 와 같다.
CREATE OR REPLACE FUNCTION nlq.can_read(tablename text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
  SELECT tablename = ANY (string_to_array(nlq._context('nlq.tables'), ','))
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA nlq FROM PUBLIC;
GRANT EXECUTE ON FUNCTION nlq.uid(), nlq.company_ids(), nlq.parent_company_ids(), nlq.has_group(text),
  nlq.can_read(text) TO :"rls_user";

COMMIT;
