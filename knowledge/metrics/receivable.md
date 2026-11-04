---
type: metric
title: 미수금
tables: [account_move]
tags: [회계]
---
미수금 = 확정된 고객 송장과 고객 환불의 미결제 잔액 합계, 부가세 포함.

```sql
SUM(amount_residual_signed)
WHERE state = 'posted' AND move_type IN ('out_invoice', 'out_refund')
```

- 다 받은 송장은 잔액이 0이라 `payment_state`로 거르지 않아도 된다. 건수를 셀 때는 `payment_state IN ('not_paid', 'partial')`.
- 환불 잔액은 음수라 미수금에서 빠진다. 부호 없는 `amount_residual`을 쓰면 환불이 더해진다([주의](../pitfalls/amount-sign.md)).
- **연체 미수금**: 위 조건 + `invoice_date_due < 오늘`. 며칠 지났는지는 `오늘 - invoice_date_due`. 오늘은 질의 시스템이 주는 기준일을 쓴다.
- 거래처별은 `commercial_partner_id`, 회사별은 `company_id`로 나눈다([회사](../pitfalls/multi-company.md)).
- 미지급금(매입 쪽)은 `move_type IN ('in_invoice','in_refund')`의 `-SUM(amount_residual_signed)`.

근거: Odoo 송장 목록의 "To pay" 필터(`account/views/account_move_views.xml`, `payment_state IN ('not_paid','partial')`)에서 고객 송장·환불의 `amount_residual_signed` 합계가 위 식과 같다. Odoo 필터는 `state != 'cancel'`이라 초안도 포함하지만, 초안은 회계에 반영되지 않았으므로 여기서는 `posted`만 센다.
관련: [매출](revenue.md), [판매 흐름](../flows/sales.md)
