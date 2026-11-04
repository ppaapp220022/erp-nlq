---
type: pitfall
title: 번역·회사별 필드는 jsonb다
tables: [product_template, product_product]
tags: [공통]
---
`product_template.name`은 문자열이 아니라 언어별 jsonb다(`{"en_US": "Office Chair"}`). 데모에는 `en_US` 키만 있다.

- 이름 출력·비교: `name->>'en_US'`. `name = 'Office Chair'`나 `name LIKE ...`는 jsonb라 맞지 않는다.
- 이름 검색: `name->>'en_US' ILIKE '%chair%'`.
- `product_product.standard_price`(원가)는 회사 id를 키로 하는 jsonb다(`{"1": 8.0}`). `(standard_price->>'1')::numeric`.
- `res_partner.name`, `res_company.name`, `sale_order.name` 같은 열은 일반 문자열이다.
