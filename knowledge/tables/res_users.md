---
type: table
title: res_users (사용자, 일부 열만)
tables: [res_users, res_partner]
tags: [공통]
---
Odoo 사용자. 담당 영업 사원 이름을 얻을 때만 쓴다. 읽을 수 있는 열은 `id`, `partner_id`, `company_id`, `active`, `share`(포털 사용자 여부)뿐이다.

- 이름은 `res_users.partner_id` → [res_partner](res_partner.md)`.name`으로 얻는다.
- 판매 주문 `user_id`, 송장 `invoice_user_id`, 발주 `user_id`가 이 테이블을 가리킨다.
