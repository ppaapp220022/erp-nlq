---
type: flow
title: 판매 흐름 (주문 → 출고 → 송장 → 수금)
tables: [sale_order, sale_order_line, stock_picking, stock_location, account_move]
tags: [판매, 재고, 회계]
---
| 단계 | 테이블과 조건 | 진행 상태 |
|---|---|---|
| 견적 | `sale_order.state IN ('draft','sent')` | |
| 주문 확정 | `sale_order.state = 'sale'` | `delivery_status`, `invoice_status` |
| 출고 | `stock_picking` 중 도착 위치 `usage = 'customer'` | `stock_picking.state`, 완료는 `done`·`date_done` |
| 송장 | `account_move.move_type = 'out_invoice'`, `state = 'posted'` | `payment_state` |
| 수금 | 수금 문서는 열려 있지 않다 | 송장 `payment_state`가 `paid`·`in_payment`, 잔액 `amount_residual_signed = 0` |
| 환불 | `move_type = 'out_refund'`, `state = 'posted'` | `reversed_entry_id` → 원 송장(비어 있을 수 있다) |

- 조인: 출고 → 주문은 `stock_picking.sale_id = sale_order.id`. 주문 ↔ 송장은 조인할 열이 없다([주의](../pitfalls/unlinked-documents.md)).
- 라인 단위 진행: `sale_order_line.qty_delivered`(출고), `qty_invoiced`(청구), `qty_to_invoice`(청구 대기).
- "미출고 주문", "청구 대기 주문"은 주문 쪽 상태 열로 답한다([출고 상태 NULL](../pitfalls/status-null.md)).
