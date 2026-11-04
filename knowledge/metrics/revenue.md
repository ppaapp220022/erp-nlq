---
type: metric
title: 매출
tables: [account_move]
tags: [회계, 판매]
---
매출 = 확정된(`state = 'posted'`) 고객 송장(`out_invoice`)에서 고객 환불(`out_refund`)을 뺀 값, 부가세 제외.

```sql
SUM(amount_untaxed_signed)
WHERE state = 'posted' AND move_type IN ('out_invoice', 'out_refund')
```

- `amount_untaxed_signed`는 환불이 음수라 더하기만 하면 빠진다. 회사 통화다.
- 기간은 `invoice_date`로 자른다. 회사가 여럿이므로 회사별로 나누거나 회사를 지정한다([주의](../pitfalls/multi-company.md)).
- "부가세 포함 매출"을 물으면 `amount_total_signed`.
- 거래처별 매출은 `commercial_partner_id`로 묶는다. 영업 사원별은 `invoice_user_id`.
- 품목별 매출은 송장 라인이 필요해서 지금은 답할 수 없다. 주문 기준 품목 매출은 아래 "수주액"으로 답하고 기준이 다르다고 밝힌다.

**수주액(주문 기준)**은 매출과 다르다. 확정 주문 라인의 부가세 제외 금액이다.
`SUM(sale_order_line.price_subtotal)`, 주문 `state = 'sale'`, `display_type IS NULL`. 기간은 `sale_order.date_order`.
질문이 "매출"이면 송장 기준, "주문 금액·수주"이면 주문 기준을 쓴다.

근거: Odoo 송장 분석 보고서(`account/report/account_invoice_report.py`, 필터 Customers·Invoiced, 측정값 `price_subtotal`)와 판매 분석 보고서(`sale/report/sale_report.py`, 필터 Sales Orders)의 합계가 위 식과 같다.
관련: [미수금](receivable.md), [account_move](../tables/account_move.md), [금액 부호](../pitfalls/amount-sign.md)
