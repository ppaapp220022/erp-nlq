#!/usr/bin/env bash
# 데모 DB에 영업 사원을 더하고 주문·송장 담당자를 나눈다 (scripts/seed_salespeople.py).
# 마지막에 사용자별로 Odoo가 보여 주는 수와 SQL로 센 수를 나란히 출력한다.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${ODOO_DB_NAME:?.env에 ODOO_DB_NAME을 넣어 주세요}"

docker compose exec -T odoo odoo shell --db_host db -r odoo -w "${ODOO_DB_PASSWORD:-odoo}" \
  -d "$ODOO_DB_NAME" --no-http --log-level=warn \
  < scripts/seed_salespeople.py
