#!/usr/bin/env bash
# CI용 축소 DB 덤프를 만든다: eval/ci/erp-ci.sql.gz (M6 CI, eval/ci/README.md)
# 질의 계층이 읽는 허용 14테이블만 담는다. 기준 스냅숏을 복원한 DB에서 실행한다.
#   - res_users는 질의 계층에 열린 열(id, partner_id, company_id, active, share)만 남긴다. 비밀번호 등은 빠진다
#   - 포털 공유 토큰(access_token)은 비운다
#   - 외래 키·인덱스(post-data)는 넣지 않는다. 빠진 테이블을 가리키기 때문이다
# 같은 DB에서 다시 만들면 같은 파일이 나온다(gzip -n, pg_dump의 무작위 \restrict 줄 제거).
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${ODOO_DB_NAME:?.env에 ODOO_DB_NAME을 넣어 주세요}"
TMP_DB="${ODOO_DB_NAME}_ci_fixture"
OUT=eval/ci/erp-ci.sql.gz
TABLES=(
  sale_order sale_order_line purchase_order purchase_order_line
  stock_picking stock_quant stock_location stock_warehouse_orderpoint
  account_move res_partner res_company product_product product_template res_users
)

in_db() { docker compose exec -T db "$@"; }

args=()
for t in "${TABLES[@]}"; do args+=(-t "public.$t"); done

in_db dropdb -U odoo --if-exists "$TMP_DB"
in_db createdb -U odoo "$TMP_DB"
trap 'in_db dropdb -U odoo --if-exists "$TMP_DB"' EXIT

in_db pg_dump -U odoo -d "$ODOO_DB_NAME" --no-owner --no-privileges --section=pre-data --section=data "${args[@]}" \
  | in_db psql -U odoo -d "$TMP_DB" -q -v ON_ERROR_STOP=1 > /dev/null

in_db psql -U odoo -d "$TMP_DB" -q -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
CREATE TABLE res_users_ci AS SELECT id, partner_id, company_id, active, share FROM res_users ORDER BY id;
DROP TABLE res_users;
ALTER TABLE res_users_ci RENAME TO res_users;
UPDATE sale_order SET access_token = NULL;
UPDATE purchase_order SET access_token = NULL;
UPDATE account_move SET access_token = NULL;
COMMIT;
SQL

in_db pg_dump -U odoo -d "$TMP_DB" --no-owner --no-privileges \
  | grep -v '^\\\(un\)\?restrict ' \
  | gzip -n -9 > "$OUT"

echo "저장: $OUT ($(wc -c < "$OUT" | tr -d ' ') bytes)"
