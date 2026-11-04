---
type: pitfall
title: 주문·출고·송장이 서로 이어지지 않을 때가 많다
tables: [sale_order, stock_picking, account_move]
tags: [판매, 회계]
---
허용된 테이블 안에서 문서끼리 직접 조인할 수 있는 것은 출고 → 판매 주문(`stock_picking.sale_id`) 하나뿐이다.

- 판매 주문 ↔ 고객 송장: 잇는 열이 없다. `account_move.invoice_origin`에 주문 번호가 텍스트로 들어갈 때가 있지만 비어 있는 경우가 많다. 주문의 청구 진행은 `sale_order.invoice_status`, `sale_order_line.qty_invoiced`로 본다.
- 출고 문서 중 `sale_id`가 비어 있는 것이 많다. "출고 건수"와 "출고된 주문 수"는 다른 질문이다.
- 고객 환불의 `reversed_entry_id`(원 송장)도 비어 있을 수 있다. 환불을 원 송장에서 빼는 대신 거래처·기간 단위로 합친다.
- 송장의 수금 여부는 `payment_state`와 `amount_residual_signed`로만 본다. 수금 문서는 열려 있지 않다.
