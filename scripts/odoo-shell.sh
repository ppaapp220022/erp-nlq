#!/usr/bin/env bash
# Python 파일을 Odoo shell(ORM, `env` 사용 가능)에서 실행한다.
#   ./scripts/odoo-shell.sh scripts/seed_salespeople.py
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${ODOO_DB_NAME:?.env에 ODOO_DB_NAME을 넣어 주세요}"
file="${1:?실행할 Python 파일을 주세요}"

docker compose exec -T odoo odoo shell --db_host db -r odoo -w "${ODOO_DB_PASSWORD:-odoo}" \
  -d "$ODOO_DB_NAME" --no-http --log-level=warn \
  < "$file" 2> >(grep -v 'extra-addons' >&2)
