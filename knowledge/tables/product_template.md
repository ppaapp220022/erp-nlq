---
type: table
title: product_template (품목)
tables: [product_template]
tags: [공통]
---
품목의 이름·종류·판매가. 변형은 [product_product](product_product.md).

- `name`은 번역 jsonb다(`{"en_US": "..."}`). `name->>'en_US'`로 꺼낸다([주의](../pitfalls/translated-jsonb.md)).
- `type`: `consu`(물품), `service`(서비스), `combo`. `is_storable`이 true인 물품만 재고 수량을 관리한다.
- `list_price`: 판매가. `categ_id`: 품목 분류. `uom_id`: 단위.
- `sale_ok`·`purchase_ok`: 판매·구매 가능 여부. `invoice_policy`: `order`(주문 수량 기준 청구)·`delivery`(출고 수량 기준).
- `default_code`, `active`, `company_id`(NULL이면 모든 회사 공용).
