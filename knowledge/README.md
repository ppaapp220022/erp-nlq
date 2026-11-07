# 도메인 지식 묶음 (OKF)

`generate`에 항상 넣는 작은 지식이다. 역할이 볼 수 있는 문서만 넣는다. 구조와 규칙은 [docs/architecture.md "지식 층"](../docs/architecture.md#지식-층-okf--rag)에 있다. 이 README는 묶음에 넣지 않는다.

| 폴더 | `type` | 내용 |
|---|---|---|
| `tables/` | `table` | 허용 테이블 13개와 `res_users` 일부 열. 질의에 쓰는 열과 값의 뜻 |
| `pitfalls/` | `pitfall` | 틀린 SQL을 만들기 쉬운 데이터 함정 |
| `flows/` | `flow` | 판매·구매 흐름과 단계별 테이블. 사람이 보는 지도는 [docs/reference/business-flows.md](../docs/reference/business-flows.md) |
| `metrics/` | `metric` | 매출·미수금 정의 |

## 쓰는 규칙

- 앞머리에 `type`, `title`, `tables`, `tags`를 쓴다. `tables`에는 문서의 SQL이 쓰는 테이블을 빠짐없이 적는다. 역할 밖 테이블이 하나라도 있으면 그 역할에는 문서 전체가 빠진다.
- `tables`에는 [db/readonly_role.sql](../db/readonly_role.sql)에서 허용한 테이블만 쓴다. 테스트(`backend/tests/test_knowledge.py`)가 앞머리 형식, 허용 테이블, 상대 링크를 검사한다.
- 데모 데이터의 건수·금액은 쓰지 않는다. 정답을 알려 주는 셈이 되고, 스냅숏이 바뀌면 틀린다. 검증한 숫자는 아래와 PR에만 남긴다.
- 평가용 질문(`eval/questions/`)이나 그 정답 SQL을 옮기지 않는다(CLAUDE.md 절대 규칙 4).
- 지표 정의는 Odoo 소스나 보고서를 근거로 적는다.

## 지표 검증

스냅숏 `erp-20261103`에서 Odoo ORM(관리자, 회사 전체 선택)의 보고서 합계와 `nlq_readonly`로 실행한 정의 SQL을 비교했다. 모두 일치한다.

| 지표 | Odoo 쪽 | 회사 1 | 회사 2 |
|---|---|---|---|
| 매출(송장 기준, 부가세 제외) | `account.invoice.report` Customers·Invoiced, `price_subtotal` | 47,574.00 | 47,574.00 |
| 수주액(주문 기준) | `sale.report` Sales Orders, `price_subtotal` | 27,660.50 | — |
| 미수금 | `account.move` To pay, 고객 송장·환불 `amount_residual_signed` | 52,074.00 | 49,299.00 |
| 연체 미수금(만기 < 2026-11-03) | 위 + `invoice_date_due < 2026-11-03` | 34,750.00 | 34,750.00 |

M5에서는 같은 비교를 사용자마다(영업 사원은 그 사람이 볼 수 있는 범위로) 다시 하고, 질의 시스템의 답까지 대조한다. Odoo 숫자는 `scripts/odoo_report_totals.py`가 [eval/odoo_reports.toml](../eval/odoo_reports.toml)로 뽑고, `nlq-report`가 대조한다. 결과는 [docs/plan.md](../docs/plan.md) "M5 Odoo 보고서 대조".
