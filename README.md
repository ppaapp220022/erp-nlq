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

2. 읽기 전용 역할(`nlq_readonly`, RLS 비교용 `nlq_rls`)과 RLS 정책을 만든다. 테이블 목록이나 `backend/nlq/identity.py`의 규칙을 고친 뒤에도 다시 실행한다.

```bash
./scripts/db-readonly-role.sh
```

3. 역할별 사용자(영업 사원 4명, 재고 담당 1명)를 만들고 주문·송장 담당자를 나눈 뒤, 평가용 기준 스냅숏을 저장한다. 데모의 Marc Demo에서 재고 그룹을 빼므로 원래 데모 설정과 다르다([ADR 0002](docs/adr/0002-separate-sales-and-stock-roles.md)).

```bash
./scripts/db-seed.sh
./scripts/db-snapshot.sh save
```

다시 같은 상태로 돌아가려면 `./scripts/db-snapshot.sh restore erp-YYYYMMDD.zip`을 실행한다.

http://localhost:8069 에 데모 관리자 계정으로 로그인할 수 있다.

4. 화면을 띄운다. API(127.0.0.1:8000)와 Next.js(127.0.0.1:3000)를 각각 실행한다. `.env`에 `ANTHROPIC_API_KEY`가 있어야 질문이 SQL로 바뀐다.

```bash
uv run --directory backend nlq-api
```

```bash
npm --prefix web install
npm --prefix web run dev
```

http://127.0.0.1:3000 에서 사용자를 고르고 질문한다. 만들어진 SQL은 고쳐서 다시 실행할 수 있고, 어느 쪽이든 `execute()`가 고른 사용자의 권한 범위를 건다. 로그인이 없는 데모라 두 서버 모두 127.0.0.1에만 연다.

## CI

PR마다 `checks`(결정적 검사)와 `ai-review`(Claude 리뷰, [.github/review/prompt.md](.github/review/prompt.md))가 돈다. 둘 다 main 브랜치 보호의 필수 체크다. `ai-review`에는 레포 시크릿 `CLAUDE_CODE_OAUTH_TOKEN`(Max 구독 토큰, `claude setup-token`으로 만든다)과 [Claude GitHub App](https://github.com/apps/claude) 설치가 필요하다.

질의 계층은 `localhost:5432`에 `NLQ_RO_USER`로 접속한다. 허용 테이블은 [db/readonly_role.sql](db/readonly_role.sql)에 있다.
