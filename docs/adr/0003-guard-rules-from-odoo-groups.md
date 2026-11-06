# 0003. guard의 행 범위: Odoo 그룹은 뽑아 오고, 규칙은 코드로 옮긴다

- 상태: 채택
- 날짜: 2026-11-06

## 맥락

guard는 테이블마다 "사용자에게 보이는 행" 조건을 끼운다. 조건은 Odoo Record Rule과 같아야 하고(M3 "Odoo 권한 일치"), 다음 두 가지가 정해져야 했다.

1. **사용자가 어느 그룹에 속하고 어느 테이블을 읽을 수 있는지**를 어디서 얻나. `nlq_readonly`는 `res_groups`, `ir_model_access`를 읽을 수 없다. 읽게 하면 질의 계층이 권한 테이블까지 보게 된다.
2. **규칙(도메인 → SQL)**을 어떻게 만드나.
3. Odoo와 같은지를 **어떻게 확인**하나. 계획에는 XML-RPC로 적었다.

## 결정

- **사실은 Odoo에서 뽑는다.** `scripts/odoo_users.py`가 사용자마다 회사, 행 범위 규칙에 걸린 그룹(`groups`), 읽기 ACL이 있는 허용 테이블(`tables`)을 `eval/users.toml`로 출력한다. `User`에 `groups`·`tables`를 더했고, 기본값이 비어 있어 목록에 없는 사용자는 아무것도 읽지 못한다.
- **규칙은 손으로 옮긴다.** `backend/nlq/identity.py`에 테이블마다 전역 규칙과 (그룹, 조건) 목록을 Odoo XML ID와 함께 적는다. 합치는 방식은 Odoo와 같다: `전역 AND (해당 그룹 규칙 OR ...)`, 해당 그룹이 없으면 전역만.
- **확인은 ORM 행 수로 한다.** `scripts/odoo_counts.py`가 `with_user(user).search_count([])`를 세어 `backend/tests/odoo_counts.toml`로 남기고, `test_odoo_scope.py`가 guard를 거친 `SELECT count(*)`와 사용자 6명 × 테이블 14개를 비교한다. Odoo가 ACL을 주지 않은 테이블은 guard가 거부해야 통과한다.
  - 보관(`active = false`) 행도 센다(`active_test=False`). 보관은 화면 필터이지 권한이 아니다.
  - 회사는 사용자가 속한 회사 전체를 고른 상태다.

## 고려한 대안

- **Odoo가 만든 SQL을 그대로 쓰기** (`_search()`의 WHERE 절): Odoo와 정확히 같지만, 생성된 SQL이 허용 목록 밖 테이블(`res_groups_users_rel` 등)을 참조할 수 있고, 규칙이 바뀌면 리뷰 없이 바뀐다. 권한 계층을 사람이 읽고 테스트할 수 있어야 해서 고르지 않았다.
- **역할 이름(`영업 사원`)으로 분기:** 한 사람이 여러 그룹을 가질 때(데모의 Marc Demo가 그랬다, ADR 0002) Odoo의 OR 합치기를 표현하지 못한다.
- **XML-RPC로 확인:** 사용자마다 비밀번호가 필요하고, Odoo 19에서 지원 중단 예정이다. 같은 ORM을 shell에서 부르는 편이 비밀번호 없이 재현된다.

## 결과

- 그룹이나 스냅숏을 바꾸면 `odoo_users.py`와 `odoo_counts.py`를 다시 돌린다. 안 돌리면 `test_odoo_scope.py`가 실패한다.
- `res_users`는 `company_ids`(다대다)를 열지 않아 `company_id`로 좁힌다. 현재 회사는 항상 `company_ids` 안에 있으므로 Odoo보다 넓어지지 않는다. 이를 위해 `res_users.share` 열 읽기 권한을 더했다(`db/readonly_role.sql`).
- 행 수가 같다는 것은 "같은 행"의 필요조건이다. 우회 시도는 `test_guard.py`가 따로 본다.
- 근거: [reference/odoo-access-rules.md](../reference/odoo-access-rules.md), Odoo 소스 `addons/*/security/*.xml`.
