---
type: table
title: stock_picking (출고·입고·이동 문서)
tables: [stock_picking, stock_location]
tags: [재고]
---
창고의 출고·입고·내부 이동 문서 하나가 한 행이다. 이름은 `WH/OUT/00001`(출고), `WH/IN/00001`(입고) 형식이다.

- 종류는 위치로 가른다. `location_id`(출발)·`location_dest_id`(도착) → [stock_location](stock_location.md)의 `usage`.
  - 고객 출고: 도착 `usage = 'customer'`
  - 공급사 입고: 출발 `usage = 'supplier'`
  - 내부 이동: 둘 다 `internal`
- `state`: `draft`, `waiting`(다른 작업 대기), `confirmed`(재고 대기), `assigned`(준비됨), `done`(완료), `cancel`.
- 날짜: `scheduled_date`(예정), `date_deadline`(기한), `date_done`(완료 일시).
- `sale_id` → [sale_order](sale_order.md). 판매 주문에서 생긴 출고만 채워진다. 구매 발주와 잇는 열은 없다(`origin`에 발주 번호가 텍스트로 들어갈 때가 있다).
- `partner_id`: 거래처. `company_id`.
