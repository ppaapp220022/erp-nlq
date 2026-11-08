#!/usr/bin/env bash
# Odoo DB에 질의 계층용 읽기 전용 역할을 만들거나 권한을 다시 맞춘다.
#   nlq_readonly: guard가 SQL을 재작성해 행 범위를 거는 경로 (기본)
#   nlq_rls:      같은 규칙을 RLS 정책이 거는 경로 (M6 비교, ADR 0005)
# 두 역할의 테이블·함수 권한은 같다(db/readonly_role.sql). 그 위에 RLS 문맥 함수와 정책을 건다.
# Odoo에서 DB를 만들고 판매·구매·재고·회계 앱을 설치한 뒤 실행한다.
# NLQ_PSQL=local이면 docker compose 대신 PATH의 psql로 접속한다(PGHOST·PGUSER 등, CI의 축소 DB용).
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
NLQ_RLS_USER="${NLQ_RLS_USER:-nlq_rls}"
NLQ_RLS_PASSWORD="${NLQ_RLS_PASSWORD:-$NLQ_RO_PASSWORD}"

psql_db() {
  local vars=(-q -v ro_user="$NLQ_RO_USER" -v rls_user="$NLQ_RLS_USER" -v db_name="$ODOO_DB_NAME")
  if [[ "${NLQ_PSQL:-docker}" == local ]]; then
    psql -d "$ODOO_DB_NAME" "${vars[@]}" "$@"
  else
    docker compose exec -T db psql -U odoo -d "$ODOO_DB_NAME" "${vars[@]}" "$@"
  fi
}

psql_db -v ro_user="$NLQ_RO_USER" -v ro_password="$NLQ_RO_PASSWORD" < db/readonly_role.sql
psql_db -v ro_user="$NLQ_RLS_USER" -v ro_password="$NLQ_RLS_PASSWORD" < db/readonly_role.sql
psql_db < db/rls_context.sql
psql_db < db/rls_policies.sql

echo "역할 $NLQ_RO_USER, $NLQ_RLS_USER 권한과 RLS 정책 적용 완료 (DB: $ODOO_DB_NAME)"
