# 읽기 전용 역할이 public 스키마에 테이블을 만들 수 있었다

- **상황:** `nlq_readonly`에는 허용 테이블 SELECT 권한만 줬다. 그런데 세션에서 `SET default_transaction_read_only = off`를 한 뒤 `CREATE TABLE t(x int)`를 실행하자 성공했다. 임시 테이블 생성도 됐다.
- **원인:** 처음에는 Postgres 15 이상이니 PUBLIC의 `public` 스키마 CREATE 권한이 기본으로 빠져 있다고 생각했다. 실제로 Odoo가 만든 DB에는 `nspacl`에 `=UC/pg_database_owner`, `datacl`에 `=Tc/odoo`가 남아 있었다. 모든 역할에 스키마 CREATE와 TEMP 권한이 열려 있던 것이다. 읽기 전용 트랜잭션 설정은 세션에서 끌 수 있어 방어선이 아니었다.
- **시도:** 처음 검증할 때는 `-c "SET ...; CREATE ..."`처럼 한 번에 실행했다. 이렇게 하면 한 트랜잭션으로 묶여 SET이 효과를 내지 못하고, 생성이 막힌 것처럼 보였다. 문장을 `-c`로 따로 나누자 문제가 드러났다.
- **해결:** [db/readonly_role.sql](../../db/readonly_role.sql)에서 `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, `REVOKE TEMPORARY ON DATABASE ... FROM PUBLIC`을 실행한다. 이후 테이블 생성, 임시 테이블 생성, UPDATE가 모두 권한 오류로 막혔다. Odoo 로그인 페이지는 계속 200으로 응답한다.
- **배운 점:** 권한은 직접 준 것만이 아니라 PUBLIC에 열린 것까지 확인해야 한다. 우회 시도는 실제 클라이언트처럼 문장을 하나씩 보내서 테스트해야 한다.

M3 우회 테스트에 "읽기 전용 설정을 끄고 쓰기/생성"을 넣는다.
