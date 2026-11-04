---
type: pitfall
title: res_partner에 회사와 담당자가 섞여 있다
tables: [res_partner]
tags: [공통]
---
거래처 회사, 그 회사의 담당자, 배송·청구 주소가 모두 `res_partner` 행이다. 문서의 `partner_id`는 회사일 수도 담당자일 수도 있다.

- "거래처별" 집계는 회사 단위로 묶는다. 송장은 `account_move.commercial_partner_id`가 이미 회사(개인 고객이면 본인)다. 주문은 `sale_order.partner_id` → `res_partner.commercial_partner_id`로 한 번 더 올라간다.
- "고객 수"를 셀 때 `res_partner` 전체를 세지 않는다. 문서에 등장한 `commercial_partner_id`를 센다.
- 회사 행은 `is_company = true`, 담당자는 `parent_id`가 있다.
