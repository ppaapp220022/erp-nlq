#!/usr/bin/env bash
# CI용 축소 덤프(eval/ci/erp-ci.sql.gz)를 빈 Postgres에 복원하고 질의용 역할과 RLS 정책을 건다.
# PATH의 psql로 접속한다(PGHOST, PGPORT, PGUSER, PGPASSWORD). PGUSER는 superuser여야 한다.
# DB 이름은 ODOO_DB_NAME(기본 erp), 역할 비밀번호는 NLQ_RO_PASSWORD.
set -euo pipefail

cd "$(dirname "$0")/.."

export ODOO_DB_NAME="${ODOO_DB_NAME:-erp}"
: "${NLQ_RO_PASSWORD:?NLQ_RO_PASSWORD를 넣어 주세요}"

dropdb --if-exists "$ODOO_DB_NAME"
createdb "$ODOO_DB_NAME"
gunzip -c eval/ci/erp-ci.sql.gz | psql -d "$ODOO_DB_NAME" -q -v ON_ERROR_STOP=1 > /dev/null
NLQ_PSQL=local ./scripts/db-readonly-role.sh
