---
type: table
title: stock_quant (위치별 재고 수량)
tables: [stock_quant, stock_location]
tags: [재고]
---
품목·위치(·로트·패키지)별 현재 수량. 재고 이동이 끝나면 갱신된다.

- `product_id` → [product_product](product_product.md), `location_id` → [stock_location](stock_location.md), `company_id`.
- `quantity`: 현재 수량. `reserved_quantity`: 출고 예약된 수량. 쓸 수 있는 수량 = `quantity - reserved_quantity`.
- **창고 재고는 `stock_location.usage = 'internal'`인 위치만 합친다.** 고객·재고조정(`inventory`) 같은 가상 위치에도 행이 있고, `inventory` 위치는 음수다. 걸지 않으면 합계가 0에 가까워진다.
- 같은 품목이 위치마다 여러 행이다. 품목별 재고는 `product_id`로 묶어 합친다.
