# erp-nlq

ERP 데이터를 한국어로 물으면 SQL로 바꿔 답하되, 사용자 권한 밖의 데이터는 LLM이 어떤 SQL을 만들어도 나오지 않게 코드로 강제하는 프로젝트.

데이터 소스는 Odoo Community 19.0 (LGPL-3.0)이며, Odoo 코드는 수정하지 않는다. DB에는 읽기 전용 역할을 추가하고, PUBLIC에 열린 스키마 생성·임시 테이블 권한만 회수한다.

## 로컬 실행

```bash
cp .env.example .env
docker compose up -d
```

1. 데모 데이터와 판매·구매·재고·회계 앱이 들어간 DB를 만든다. Odoo 19는 기본값이 데모 데이터 없음이라 `--with-demo`가 필요하다.

```bash
set -a; source .env; set +a
docker compose exec -T odoo odoo server --db_host db -r odoo -w "$ODOO_DB_PASSWORD" \
  -d "$ODOO_DB_NAME" -i sale_management,purchase,stock,account \
  --with-demo --stop-after-init --http-port 8070
```

2. 읽기 전용 역할을 만든다. 테이블 목록을 고친 뒤에도 다시 실행한다.

```bash
./scripts/db-readonly-role.sh
```

3. 영업 사원을 추가하고 주문·송장 담당자를 나눈 뒤, 평가용 기준 스냅숏을 저장한다.

```bash
./scripts/db-seed.sh
./scripts/db-snapshot.sh save
```

다시 같은 상태로 돌아가려면 `./scripts/db-snapshot.sh restore erp-YYYYMMDD.zip`을 실행한다.

http://localhost:8069 에 데모 관리자 계정으로 로그인할 수 있다.

질의 계층은 `localhost:5432`에 `NLQ_RO_USER`로 접속한다. 허용 테이블은 [db/readonly_role.sql](db/readonly_role.sql)에 있다.
