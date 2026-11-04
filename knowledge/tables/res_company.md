---
type: table
title: res_company (회사)
tables: [res_company]
tags: [공통]
---
Odoo 안의 회사(법인). 거의 모든 문서에 `company_id`가 있다.

- `name`, `currency_id`, `partner_id`(회사 자신의 거래처 행), `parent_id`(상위 회사).
- 데모에는 회사가 3개 있다. 회사마다 문서 번호를 따로 매긴다([주의](../pitfalls/multi-company.md)).
