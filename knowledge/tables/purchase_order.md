---
type: table
title: purchase_order (구매 발주)
tables: [purchase_order]
tags: [구매]
---
견적 요청(RFQ)과 확정 발주의 머리. 라인은 [purchase_order_line](purchase_order_line.md).

- `name`: 발주 번호(P00001 형식). `partner_id` → [res_partner](res_partner.md) 공급사, `user_id` → 구매 담당자, `company_id`.
- `state`: `draft`(견적 요청), `sent`(보냄), `to approve`(승인 대기), `purchase`(확정 발주), `cancel`. "발주"는 보통 `state = 'purchase'`다.
- 날짜: `date_order`(주문일), `date_approve`(확정일), `date_planned`(입고 예정일), `effective_date`(첫 입고 완료일).
- 금액: `amount_untaxed`, `amount_tax`, `amount_total`.
- `receipt_status`: `pending`(미입고)·`partial`·`full`, 또는 NULL(입고 문서 없음, [주의](../pitfalls/status-null.md)).
- `invoice_status`: `no`·`to invoice`(매입 송장 대기)·`invoiced`.
