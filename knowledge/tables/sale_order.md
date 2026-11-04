---
type: table
title: sale_order (판매 주문)
tables: [sale_order]
tags: [판매]
---
판매 견적과 주문의 머리. 한 행이 주문 하나다. 라인은 [sale_order_line](sale_order_line.md).

- `name`: 주문 번호(S00001 형식). `partner_id` → [res_partner](res_partner.md) 고객, `user_id` → [res_users](res_users.md) 담당 영업 사원(NULL이면 담당자 없음), `company_id` → [res_company](res_company.md).
- `state`: `draft`(견적), `sent`(견적 보냄), `sale`(확정 주문), `cancel`. "주문"은 보통 `state = 'sale'`이다.
- `date_order`: 주문 일시(timestamp). 확정 전에는 견적 일시.
- 금액: `amount_untaxed`(부가세 제외), `amount_tax`, `amount_total`(부가세 포함). 주문 통화 기준.
- `delivery_status`: `pending`·`started`·`partial`·`full`, 또는 NULL. NULL은 출고 문서가 없다는 뜻이다([주의](../pitfalls/status-null.md)).
- `invoice_status`: `no`(청구할 것 없음), `to invoice`(청구 대기), `invoiced`(청구 완료), `upselling`.
- `commitment_date`: 약속 배송일. `effective_date`: 첫 출고 완료일.
