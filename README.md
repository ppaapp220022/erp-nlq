# erp-nlq

ERP 데이터를 한국어로 물으면 SQL로 바꿔 답하되, 사용자 권한 밖의 데이터는 LLM이 어떤 SQL을 만들어도 나오지 않게 코드로 강제하는 프로젝트.

데이터 소스는 Odoo Community 19.0 (LGPL-3.0)이며, Odoo 코드는 수정하지 않는다.

## 로컬 실행

```bash
docker compose up -d
```

http://localhost:8069 에서 DB를 만들 때 "Demo data"를 켠다.
