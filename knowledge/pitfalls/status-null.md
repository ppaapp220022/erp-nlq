---
type: pitfall
title: 출고·입고 상태가 NULL이면 문서가 없는 것이다
tables: [sale_order, purchase_order]
tags: [판매, 구매]
---
`sale_order.delivery_status`와 `purchase_order.receipt_status`는 연결된 출고·입고 문서가 없으면 NULL이다. "아직 출고 전"이 아니다. 서비스 품목만 있는 주문, 출고 문서가 만들어지지 않은 주문이 여기에 든다.

- 출고 문서가 있고 하나도 끝나지 않음: `delivery_status = 'pending'` (입고는 `receipt_status = 'pending'`).
- 출고가 끝나지 않은 확정 주문 전부: `state = 'sale' AND (delivery_status IS NULL OR delivery_status <> 'full')`. NULL을 빼고 싶으면 질문 의도를 따른다.
- `delivery_status <> 'full'`만 쓰면 NULL 행이 빠진다(SQL에서 NULL 비교는 참이 아니다).
- `invoice_status`는 NULL이 없고 `no`가 기본값이다.
