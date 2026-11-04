---
type: table
title: stock_warehouse_orderpoint (재주문 규칙, 안전 재고)
tables: [stock_warehouse_orderpoint]
tags: [재고]
---
품목·위치별 최소·최대 재고 규칙.

- `product_id` → [product_product](product_product.md), `location_id` → [stock_location](stock_location.md), `company_id`.
- `product_min_qty`: 최소(안전) 재고. 이 아래로 내려가면 보충 대상이다. `product_max_qty`: 보충 목표.
- `trigger`: `auto`·`manual`. `active`가 false인 규칙은 쓰지 않는다.
- 안전 재고 미달 품목 = 해당 위치의 internal 재고([stock_quant](stock_quant.md) 합계)가 `product_min_qty`보다 작은 품목.
