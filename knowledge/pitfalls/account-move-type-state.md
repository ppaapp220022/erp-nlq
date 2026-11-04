---
type: pitfall
title: account_move는 move_type과 state를 함께 건다
tables: [account_move]
tags: [회계]
---
송장, 환불, 일반 전표가 한 테이블에 있다. 조건 없이 세면 전표까지 섞인다.

- 고객 송장 `out_invoice`, 고객 환불 `out_refund`, 매입 송장 `in_invoice`, 매입 환불 `in_refund`. `entry`는 송장이 아니다.
- 확정된 것만: `state = 'posted'`. `draft`는 아직 회계에 반영되지 않았고 `cancel`은 취소됐다.
- "송장"이라고만 하면 고객 송장(`out_invoice`)이다. "매입 송장", "공급사 청구서"는 `in_invoice`.
- 환불을 빼야 하는 합계(매출 등)는 송장과 환불을 함께 거르고 부호 있는 금액을 쓴다([금액 부호](amount-sign.md)).
