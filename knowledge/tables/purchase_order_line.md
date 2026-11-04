---
type: table
title: purchase_order_line (구매 발주 라인)
tables: [purchase_order_line]
tags: [구매]
---
발주의 품목 줄. `order_id` → [purchase_order](purchase_order.md), `product_id` → [product_product](product_product.md), `partner_id`는 발주 공급사.

- `display_type`: NULL이면 품목 줄. 합칠 때 `display_type IS NULL`을 건다.
- 수량: `product_qty`(발주 수량), `qty_received`(입고), `qty_invoiced`(매입 송장), `qty_to_invoice`. 미입고 수량 = `product_qty - qty_received`.
- 금액: `price_unit`, `discount`, `price_subtotal`(부가세 제외), `price_total`.
- `date_planned`: 라인별 입고 예정일. `company_id`가 라인에도 있다.
