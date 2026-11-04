---
type: pitfall
title: 송장 금액 열의 부호
tables: [account_move]
tags: [회계]
---
`account_move`의 금액 열은 두 벌이다.

| 열 | 부호 | 통화 |
|---|---|---|
| `amount_untaxed`, `amount_total`, `amount_residual` | 없음. 환불도 양수 | 문서 통화 |
| `amount_untaxed_signed`, `amount_total_signed`, `amount_residual_signed` | 고객 송장 +, 고객 환불 −, 매입 송장 −, 매입 환불 + | 회사 통화 |

- 송장과 환불을 함께 합칠 때는 `_signed` 열을 쓴다. 부호 없는 열을 합치면 환불이 더해진다.
- 매입 쪽 합계를 양수로 보이려면 `-SUM(amount_total_signed)`처럼 부호를 뒤집는다.
- 송장 한 건의 금액을 보여 줄 때는 부호 없는 열이 자연스럽다.
