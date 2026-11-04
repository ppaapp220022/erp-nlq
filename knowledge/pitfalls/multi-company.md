---
type: pitfall
title: 회사가 여럿이고 문서 번호가 회사마다 겹친다
tables: [account_move, res_company]
tags: [공통, 회계]
---
데모에는 회사가 3개 있다. 고객·매입 송장은 회사 두 곳에 같은 번호(`INV/2026/00001` 등)로 따로 있다. 판매·구매·재고 문서는 한 회사에만 있다.

- 문서 번호(`name`)는 회사 안에서만 고유하다. 번호로 조인하거나 셀 때는 `company_id`도 함께 쓴다.
- 회사 조건 없이 송장 금액을 합치면 같은 거래가 두 번 더해진다. 질문에 회사가 없으면 결과를 `company_id`(또는 회사 이름)별로 나눠 보여 준다.
- 회사 이름은 [res_company](../tables/res_company.md)`.name`.
