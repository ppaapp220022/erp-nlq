---
type: table
title: product_product (품목 변형)
tables: [product_product, product_template]
tags: [공통]
---
주문·재고 라인이 가리키는 품목. 이름·종류·가격은 템플릿([product_template](product_template.md))에 있다.

- `product_tmpl_id` → `product_template.id`. 품목 이름은 이 조인으로 얻는다.
- `default_code`: 내부 참조 코드(비어 있을 수 있다). `barcode`.
- `active`: 보관 처리된 품목은 false.
- `standard_price`(원가)는 회사별 jsonb다(`{"1": 8.0}`, 키는 회사 id 문자열). `(standard_price->>'1')::numeric`처럼 꺼낸다.
