# 0008. 질의 경로: Odoo ORM API 대신 SQL을 만들고 execute()가 권한을 건다

- 상태: 채택
- 날짜: 2026-11-09 (M1에 정한 방향을 마무리 단계에서 기록한다)

## 맥락

[ADR 0001](0001-odoo-as-data-source.md)은 "ORM API 대신 SQL을 택한 이유는 별도 ADR로 남긴다"고 했다. plan.md의 위험 표에도 "Odoo ORM API를 쓰면 권한이 자동 적용되지 않나"라는 반론이 있다.

반론은 맞는 말이다. Odoo ORM은 `with_user(user)`로 부르면 ACL과 Record Rule을 스스로 건다. 외부에서도 Odoo 19의 JSON-2 API(`/json/2/<모델>/<메서드>`, 사용자 API 키를 Bearer로 보냄)로 `search_read`·`read_group`을 부르면 그 사용자의 권한으로 읽는다. 그런데도 이 프로젝트는 LLM이 SQL을 만들고, 권한은 우리 코드(`execute()`)가 건다. 그 이유를 정리한다.

## 결정

- 질문은 **SQL**로 바꾼다. 권한은 `execute()`가 구문 트리 재작성(guard) 또는 RLS 정책으로 건다(ADR [0003](0003-guard-rules-from-odoo-groups.md), [0005](0005-rls-vs-guard.md)).
- Odoo ORM은 **질의 경로에 쓰지 않는다.** 대신 우리 계층이 Odoo와 같은지 확인하는 기준으로 쓴다. `odoo shell`에서 사용자별 행 수(`scripts/odoo_counts.py`)와 보고서 합계(`scripts/odoo_report_totals.py`)를 뽑는다.

## 고려한 대안

- **LLM이 JSON-2 API 호출(모델·도메인·`read_group`)을 만들고, 사용자 API 키로 부른다.** 권한은 Odoo가 건다. 고르지 않은 이유:
  - 표현력. `read_group`은 한 모델 안의 묶음·합계다. 여러 모델 조인, 조건별 합계(`FILTER`), 날짜 구간 나누기, 서브쿼리를 한 번에 하지 못한다. 평가 문항에는 이런 질문이 있다(예: account-008 미수금 만기 구간). 호출을 여러 번 나눠 결과를 코드로 합치면, 그 합치는 코드도 LLM이 만들게 되고 신뢰하지 않는 실행 경로가 하나 더 생긴다.
  - 비교 축. 이 프로젝트는 자연어 → SQL 도구(비교 대상 WrenAI 등)가 만든 **임의의 SQL**에서도 권한이 지켜지는지를 잰다. 같은 축에서 재야 정확도·우회 건수를 나란히 놓을 수 있다.
  - 운영. 사용자마다 API 키를 발급하고 보관해야 한다. XML-RPC·JSON-RPC는 Odoo 19에서 지원 중단되고 22에서 제거 예정이라(컨테이너 안 `odoo/addons/rpc/controllers/__init__.py`), 외부 호출은 JSON-2만 남는다.
- **LLM이 ORM Python 코드를 만들고 `odoo shell`에서 실행한다.** 표현력은 충분하지만, 임의 코드 실행이다. 생성 코드가 `sudo()`나 `env.cr.execute()`로 규칙을 건너뛸 수 있고, shell의 DB 접속은 superuser `odoo`다. 신뢰 경계를 그을 곳이 없다.
- **LLM은 도메인만 만들고, 서버가 `with_user(user).search_read(domain)`를 부른다.** 안전하지만 표현력이 첫째 대안과 같다.

## 결과

- **규칙을 직접 옮긴다.** Odoo가 자동으로 해 주던 Record Rule 합치기를 `identity.py`에 다시 쓴다. Odoo 규칙이 바뀌면 갈라질 수 있으므로 테스트로 지킨다. 행 수는 사용자 6명 × 테이블 14개(84/84, `test_odoo_scope.py`), 금액은 보고서 대조 17/17(`test_report_check.py`)로 비교한다.
- **ORM이 주던 것을 SQL에서 따로 다룬다.**
  - 저장되지 않는 계산 필드는 DB에 없다. OKF 문서가 저장된 열로 같은 값을 구하는 법을 적는다(예: 매출·미수금 정의).
  - 번역 필드는 jsonb다(`name->>'en_US'`, `knowledge/pitfalls/translated-jsonb.md`).
  - 필드 단위 권한(필드의 `groups=`)은 SQL에 없다. 대신 열 단위 GRANT를 쓴다(`res_users`는 5개 열만 연다). 허용 테이블의 나머지 열에 필드 단위 제한이 있는지는 따로 대조하지 않았다.
- **얻는 것.** LLM 출력이 무엇이든 DB에 닿는 길은 `execute()` 하나이고(절대 규칙 1), 그 안의 규칙을 사람이 읽고 테스트할 수 있다. 같은 규칙을 guard와 RLS 두 방식으로 걸어 비교할 수 있었다(ADR 0005). WrenAI가 만든 SQL도 같은 `execute()`로 실행해, 범위를 걸면 우회가 0이 되는 것을 보였다(plan.md "M6 WrenAI 비교").
- **재지 않은 것.** ORM API 방식으로 같은 50문항을 풀었을 때의 정확도는 재지 않았다. "ORM API 방식 비교"로 plan.md 2차 목록에 둔다.
- 근거: Odoo 19 소스(컨테이너 안 `/usr/lib/python3/dist-packages/odoo`)의 `addons/rpc/controllers/json2.py`(`auth='bearer'`), `addons/rpc/controllers/__init__.py`(`RPC_DEPRECATION_NOTICE`), `orm/models.py`(`read_group`).
