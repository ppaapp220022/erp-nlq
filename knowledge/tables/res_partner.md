---
type: table
title: res_partner (거래처·담당자·주소)
tables: [res_partner]
tags: [공통]
---
고객, 공급사, 그 회사의 담당자, 배송 주소가 모두 한 테이블에 있다([주의](../pitfalls/res-partner-mixed.md)).

- `name`, `complete_name`(`회사, 담당자` 형식), `email`, `phone`, `city`, `country_id`.
- `is_company`: 회사이면 true. `parent_id`: 담당자·주소가 속한 회사. `commercial_partner_id`: 자기 자신이 회사이면 자기, 아니면 소속 회사.
- `type`: `contact`, `invoice`, `delivery`, `other`.
- `customer_rank`·`supplier_rank`: 판매·구매 문서에 쓰인 횟수. 0보다 크면 고객·공급사로 쓰인 적이 있다.
- 사용자([res_users](res_users.md))와 회사([res_company](res_company.md))도 각자 이 테이블에 거래처 행을 가진다.
