# 0005. 행 범위: guard 재작성과 RLS 정책을 같은 규칙으로 두고 비교한다

- 상태: 채택
- 날짜: 2026-11-08

## 맥락

M3의 guard는 sqlglot 트리에서 테이블마다 행 범위 서브쿼리를 끼운다(ADR 0003). M6에서는 같은 규칙을 Postgres RLS로 구현해 비교하기로 했다. 정해야 할 것은 다음이다.

1. 규칙을 두 군데 따로 쓰면 언젠가 갈라진다. 어디서 한 번만 쓰나.
2. RLS는 테이블에 켜면 그 테이블을 읽는 모든 비-superuser 역할에 걸린다. guard 경로(`nlq_readonly`)와 RLS 경로를 어떻게 함께 재나.
3. 정책은 사용자를 모른다. 사용자 값(uid, 회사, 그룹, ACL)을 어떻게 넘기고, 사용자 SQL이 그 값을 바꾸지 못하게 하나.
4. Odoo의 합치기 규칙을 정책 식 하나로 어떻게 옮기나.

근거가 된 Odoo 소스는 컨테이너 안 `odoo/addons/base/models/ir_rule.py`(19.0)다.
- `_get_rules`: 사용자 그룹에 걸린 규칙과 전역 규칙(`r.global`)을 고른다. superuser 환경(`env.su`)이면 규칙이 없다.
- `_compute_domain`: 그룹이 있는 규칙은 `group_domains`, 없는 규칙은 `global_domains`에 넣고, `Domain.AND(global_domains + [Domain.OR(group_domains)])`로 합친다. 해당 그룹 규칙이 하나도 없으면 전역만 남는다. `_inherits` 부모 모델의 규칙도 전역으로 더한다(`product.product` → `product.template`).

## 결정

- **규칙은 `backend/nlq/identity.py` 하나다.** guard는 지금처럼 사용자별로 풀어서 끼우고, `backend/nlq/rls.py`가 같은 `TABLES`를 정책 SQL(`db/rls_policies.sql`)로 바꾼다. 생성 파일이 규칙과 다르면 `test_rls.py`가 실패한다.
- **Odoo 합치기는 식으로 옮긴다.** 정책은 사용자를 모르는 채 한 번 만들어 두므로, 그룹 판별을 식 안에서 한다.
  `can_read(t) AND 전역 AND (NOT (그룹1 OR 그룹2 ...) OR (그룹1 AND 조건1) OR (그룹2 AND 조건2) ...)`
  Odoo ACL(테이블 읽기 권한)도 `nlq.can_read`로 함께 건다. guard 없이도 정책만으로 Odoo와 같은 범위가 된다.
- **역할을 둘로 나눈다.** `nlq_readonly`는 guard 경로이고 정책은 `USING (true)`다. 새 역할 `nlq_rls`는 정책이 범위를 거는 경로다. 두 역할의 테이블·함수 권한은 같은 `db/readonly_role.sql`로 준다. 방식은 `NLQ_ENFORCE=guard|rls|both`로 고르고 기본은 `guard`다.
  - `rls`: guard는 검증(문장 하나, 노드·함수·형 허용 목록, 테이블 허용 목록과 ACL, LIMIT)만 하고 재작성은 하지 않는다.
  - `both`: guard 재작성과 RLS 정책을 함께 건다.
- **사용자 문맥은 `SET LOCAL nlq.*`로 넘기고, SECURITY DEFINER 함수로만 읽는다.** `execute()`가 트랜잭션마다 `nlq.uid`, `nlq.company_ids`, `nlq.groups`, `nlq.tables`를 넣는다(`db/rls_context.sql`).
  - 사용자 SQL은 값을 바꾸지 못한다. 서버 커서가 SELECT 하나만 받고, `set_config`·`current_setting`은 두 역할 모두 실행 권한이 없다(PUBLIC에서 회수).
  - 문맥이 비어 있으면 함수가 오류를 낸다. `execute()`를 거치지 않고 `nlq_rls`로 접속해도 행이 아니라 오류가 나온다(실패 시 닫힘). 전역 규칙이 `TRUE`인 `res_company`도 `can_read`가 먼저 문맥을 요구한다.
  - `parent_of`(상위 회사)는 함수 `nlq.parent_company_ids()`가 소유자 권한으로 읽는다. 정책 안에서 `res_company`를 직접 읽으면 `res_company` 정책이 다시 걸려 상위 회사가 빠질 수 있다. Odoo도 규칙 도메인을 `sudo()`로 평가한다.
- **`FORCE ROW LEVEL SECURITY`는 쓰지 않는다.** Odoo는 superuser `odoo`로 접속해 RLS를 건너뛴다. 정책을 켠 뒤 Odoo ORM 행 수(`scripts/odoo_counts.py`)를 다시 뽑아 기존 기준 파일과 같음을 확인했다.

## 비교 (2026-11-08, 스냅숏 `erp-20261103.zip`)

| 항목 | guard | RLS | 둘 다 |
|---|---|---|---|
| Odoo 행 수 일치 (사용자 6명 × 테이블 14개, `test_odoo_scope.py`) | 84/84 | 84/84 | 84/84 |
| 우회 테스트 (`test_guard.py` DB 테스트, guard 없이 RLS만도 함께) | 통과 | 통과 | 통과 |
| 평가·예시 SQL 90개 × 사용자 6명의 결과 | 기준 | 같음 | 같음 |
| 같은 540회 실행 시간 (접속 포함, 3회 중앙값 합) | 3.06초 | 3.34초 | 3.60초 |
| 오류 문구로 권한 밖 값이 새지 않음 | 플래너 순서에 기댐 | 보장 | 보장 |
| 정책을 우회하는 길 | guard 파서·재작성의 빈틈 | 문맥 값 조작(막혀 있음), superuser 접속 | 두 길을 모두 뚫어야 함 |
| 화면의 "SQL 보기" | 재작성한 SQL | 모델이 낸 SQL 그대로 | 재작성한 SQL |

- 결과 비교에서 다른 것은 1건이었다. 예시 `ex-sales-002`가 `ORDER BY lines DESC LIMIT 3`에서 라인 수 2인 주문이 동점이라 어느 것이 셋째로 오는지가 실행마다 달랐다. 범위 차이가 아니다.
- **오류 누출:** guard 경로에서는 행 범위 조건과 사용자 조건이 같은 Filter에 들어가고, 평가 순서는 플래너 비용에 따른다(architecture.md "guard"). RLS 정책 조건은 security barrier라 leakproof가 아닌 사용자 조건(형 변환, 나누기)보다 먼저 평가된다. `EXPLAIN`에서 정책 조건 뒤에 `(name)::boolean`이 오는 것을 확인했다.
- **시간:** 데모 데이터는 작아서(주문 24건) 차이가 접속 시간에 묻힌다. 정책이 행마다 `nlq.has_group` 같은 함수를 부르므로 큰 테이블에서는 차이가 커질 수 있다. 재지 않았다.

## 고려한 대안

- **역할 하나 + 방식 GUC:** 정책 안에 `nlq.enforce = 'guard'`면 통과하는 조건을 둔다. 정책 자체에 끄는 스위치가 생기고, 그 스위치가 사용자 문맥과 같은 세션 값이라 고르지 않았다. 역할로 나누면 경로가 접속 시점(인증)에 정해진다.
- **사용자마다 DB 역할을 만들고 `current_user`로 판별:** 문맥 함수가 필요 없지만, Odoo 사용자와 DB 역할을 동기화해야 하고 접속 풀을 사용자마다 따로 둬야 한다.
- **`current_setting`을 `nlq_rls`에만 열기:** SECURITY DEFINER 함수가 필요 없지만, guard가 없으면 사용자 SQL이 `is_superuser` 같은 다른 설정도 읽는다.
- **정책을 손으로 쓰기:** 규칙이 두 군데가 되어 언젠가 갈라진다. 생성 파일과 동기화 테스트를 택했다.

## 결과

- 기본 방식은 `guard`로 둔다. M4·M5의 점수는 모두 guard로 쟀다. 운영 기본값을 `both`로 바꿀지는 따로 정한다. `both`는 두 층을 모두 뚫어야 새고 오류 누출을 보장하지만, `nlq_rls`와 정책이 깔린 DB가 필요하다.
- 절대 규칙 2의 "질의 계층 역할"에 `nlq_rls`가 더해진다. 두 역할 모두 superuser·BYPASSRLS가 아니어야 하고, `execute()`가 접속할 때 확인한다.
- `identity.py`를 바꾸면 `python -m nlq.rls > db/rls_policies.sql`과 `./scripts/db-readonly-role.sh`를 다시 실행한다.
- 스냅숏을 복원하면 `db-snapshot.sh`가 역할 스크립트를 다시 돌려 정책을 맞춘다.
