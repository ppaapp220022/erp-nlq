---
type: table
title: account_move (송장·환불·전표)
tables: [account_move]
tags: [회계]
---
회계 문서 머리. 고객 송장, 매입 송장, 환불, 일반 전표가 모두 이 테이블에 있다. 라인(`account_move_line`)은 열려 있지 않다.

- `move_type`: `out_invoice`(고객 송장), `out_refund`(고객 환불), `in_invoice`(매입 송장), `in_refund`(매입 환불), `entry`(일반 전표, 송장 아님), `out_receipt`·`in_receipt`.
- `state`: `draft`, `posted`(확정), `cancel`. 집계에는 보통 `posted`만 쓴다([주의](../pitfalls/account-move-type-state.md)).
- `name`: 문서 번호(INV/2026/00001, RINV/…, BILL/…). 회사마다 따로 매긴다.
- `partner_id` → 거래처, `commercial_partner_id` → 거래처의 회사. `invoice_user_id` → 담당 영업 사원. `company_id`.
- 날짜: `invoice_date`(송장일), `invoice_date_due`(만기일), `date`(회계일).
- 금액(문서 통화, 부호 없음): `amount_untaxed`, `amount_tax`, `amount_total`, `amount_residual`(미결제 잔액).
- 금액(회사 통화, 부호 있음): `amount_untaxed_signed`, `amount_total_signed`, `amount_residual_signed`. 고객 환불과 매입 송장이 음수다. 합칠 때는 이쪽을 쓴다([주의](../pitfalls/amount-sign.md)).
- `payment_state`: `not_paid`, `partial`, `in_payment`(지급 등록, 은행 대사 전), `paid`, `reversed`(환불로 상쇄), `blocked`.
- `reversed_entry_id`: 환불이 가리키는 원 송장. `invoice_origin`: 원천 문서 번호 텍스트(주문 번호 등, 비어 있을 수 있다).
