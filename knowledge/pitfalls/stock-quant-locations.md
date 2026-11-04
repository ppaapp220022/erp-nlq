---
type: pitfall
title: 재고 수량은 internal 위치만 합친다
tables: [stock_quant, stock_location]
tags: [재고]
---
`stock_quant`에는 창고 위치뿐 아니라 고객·재고조정 같은 가상 위치의 행도 있다. 재고 조정 위치(`inventory`)는 음수라, 전부 합치면 0 근처가 된다.

- 현재 재고: `stock_quant JOIN stock_location ON location_id = stock_location.id WHERE stock_location.usage = 'internal'`.
- 창고 하나로 좁힐 때는 `stock_location.warehouse_id`나 `complete_name LIKE 'WH/%'`.
- 출고 가능 수량은 `quantity - reserved_quantity`.
