---
type: table
title: sale_order_line (판매 주문 라인)
tables: [sale_order_line]
tags: [판매]
---
판매 주문의 품목 줄. `order_id` → [sale_order](sale_order.md).

- `product_id` → [product_product](product_product.md). `name`은 라인 설명 텍스트다.
- `display_type`: NULL이면 품목 줄, 값이 있으면(`line_section`·`line_subsection`·`line_note`) 제목·메모 줄이라 품목·금액이 없다. 수량·금액을 합칠 때는 `display_type IS NULL`을 건다.
- 수량: `product_uom_qty`(주문 수량), `qty_delivered`(출고), `qty_invoiced`(청구), `qty_to_invoice`(청구 대기).
- 금액: `price_unit`, `discount`(%), `price_subtotal`(부가세 제외), `price_total`(포함). `untaxed_amount_invoiced`는 청구된 부가세 제외 금액.
- `state`는 주문의 `state`를 복사한 열이다. `salesman_id`는 주문의 `user_id`, `order_partner_id`는 주문 고객이다.
- `company_id`가 라인에도 있다.
