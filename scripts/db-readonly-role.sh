#!/usr/bin/env bash
# Odoo DB에 질의 계층용 읽기 전용 역할을 만들거나 권한을 다시 맞춘다.
# Odoo에서 DB를 만들고 판매·구매·재고·회계 앱을 설치한 뒤 실행한다.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${ODOO_DB_NAME:?.env에 ODOO_DB_NAME(Odoo에서 만든 DB 이름)을 넣어 주세요}"
: "${NLQ_RO_PASSWORD:?.env에 NLQ_RO_PASSWORD를 넣어 주세요}"
NLQ_RO_USER="${NLQ_RO_USER:-nlq_readonly}"

docker compose exec -T db psql -U odoo -d "$ODOO_DB_NAME" -q \
  -v ro_user="$NLQ_RO_USER" \
  -v ro_password="$NLQ_RO_PASSWORD" \
  -v db_name="$ODOO_DB_NAME" \
  < db/readonly_role.sql

echo "역할 $NLQ_RO_USER 권한 적용 완료 (DB: $ODOO_DB_NAME)"
