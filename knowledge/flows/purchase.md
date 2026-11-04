---
type: flow
title: 구매 흐름 (발주 → 입고 → 매입 송장 → 지급)
tables: [purchase_order, purchase_order_line, stock_picking, stock_location, account_move]
tags: [구매, 재고, 회계]
---
| 단계 | 테이블과 조건 | 진행 상태 |
|---|---|---|
| 견적 요청 | `purchase_order.state IN ('draft','sent','to approve')` | |
| 발주 확정 | `purchase_order.state = 'purchase'` | `receipt_status`, `invoice_status` |
| 입고 | `stock_picking` 중 출발 위치 `usage = 'supplier'` | `stock_picking.state`, 완료는 `done`·`date_done` |
| 매입 송장 | `account_move.move_type = 'in_invoice'`, `state = 'posted'` | `payment_state` |
| 지급 | 지급 문서는 열려 있지 않다 | 매입 송장 `payment_state`, `amount_residual_signed` |
| 매입 환불 | `move_type = 'in_refund'` | `reversed_entry_id` |

- 발주와 입고·매입 송장을 잇는 열은 없다. `stock_picking.origin`, `account_move.invoice_origin`에 발주 번호가 텍스트로 들어갈 때가 있지만 믿을 수 없다.
- 라인 단위 진행: `purchase_order_line.qty_received`(입고), `qty_invoiced`(매입 송장). 미입고 수량 = `product_qty - qty_received`.
- "입고 안 된 발주"는 `receipt_status`로 답한다([입고 상태 NULL](../pitfalls/status-null.md)).
