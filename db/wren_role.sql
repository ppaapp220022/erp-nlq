-- 비교 기준 2(M6)에서 WrenAI가 접속하는 역할. 질의 계층은 쓰지 않는다(CLAUDE.md 절대 규칙 2).
-- docs/reference/wrenai.md의 명령이 psql 변수 wren_user, wren_password, ro_user, db_name 을 넘겨 실행한다.
--
-- WrenAI(ibis-server)는 쿼리마다 CREATE TEMPORARY VIEW로 결과 열의 형을 읽는다. nlq_readonly는
-- 읽기 전용 트랜잭션이고 임시 객체 권한이 없어(db/readonly_role.sql) 연결 확인부터 실패한다.
-- 그래서 nlq_readonly의 멤버로 만들어 읽을 수 있는 테이블·열·행은 똑같이 두고, 임시 객체만 더 연다.
--   - 테이블 SELECT 권한은 INHERIT로 nlq_readonly에서 받는다. 직접 준 테이블 권한은 없다.
--   - RLS 정책 nlq_guard(TO nlq_readonly, USING true)는 멤버에게도 적용된다. 행 범위는 없다.
--   - 쓰기 권한이 있는 테이블이 없으므로 읽기 전용 설정을 끄고도 임시 객체 밖에는 쓸 수 없다.

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE %I LOGIN', :'wren_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'wren_user') \gexec

ALTER ROLE :"wren_user" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS
  PASSWORD :'wren_password';
ALTER ROLE :"wren_user" SET default_transaction_read_only = off;

GRANT :"ro_user" TO :"wren_user";
GRANT CONNECT, TEMPORARY ON DATABASE :"db_name" TO :"wren_user";
