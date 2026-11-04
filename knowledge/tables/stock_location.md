---
type: table
title: stock_location (재고 위치)
tables: [stock_location]
tags: [재고]
---
창고 안의 선반부터 고객·공급사 같은 가상 위치까지 모든 위치.

- `usage`: `internal`(실제 창고 위치), `customer`, `supplier`, `inventory`(재고 조정), `production`, `transit`, `view`(묶음용, 재고 없음).
- `complete_name`: `WH/Stock/Shelf 1` 같은 전체 경로. `name`은 마지막 이름만.
- `location_id`: 상위 위치. `warehouse_id`: 속한 창고. `company_id`는 가상 위치에서 NULL일 수 있다.
