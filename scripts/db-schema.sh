#!/usr/bin/env bash
# nlq_readonly가 읽을 수 있는 열 목록을 db/schema.txt로 뽑는다. generate()의 프롬프트에 들어간다.
# generate()는 DB에 접속하지 않으므로(절대 규칙 1) 열 목록은 이 파일로만 넘긴다.
# 허용 테이블(db/readonly_role.sql)이나 Odoo 모듈이 바뀌면 다시 실행해 커밋한다.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${ODOO_DB_NAME:?.env에 ODOO_DB_NAME을 넣어 주세요}"
: "${NLQ_RO_PASSWORD:?.env에 NLQ_RO_PASSWORD를 넣어 주세요}"

# 권한이 있는 열만 고른다(res_users는 일부 열만). message_* 는 Odoo 채터 내부 열이라 뺀다.
docker compose exec -T -e PGPASSWORD="$NLQ_RO_PASSWORD" db \
  psql -h 127.0.0.1 -U "${NLQ_RO_USER:-nlq_readonly}" -d "$ODOO_DB_NAME" -At -c "
  SELECT c.table_name || '(' || string_agg(c.column_name || ' ' || c.udt_name, ', ' ORDER BY c.ordinal_position) || ')'
  FROM information_schema.columns c
  WHERE c.table_schema = 'public'
    AND has_column_privilege(current_user, format('%I', c.table_name), c.column_name, 'SELECT')
    AND c.column_name NOT LIKE 'message\_%'
  GROUP BY c.table_name
  ORDER BY c.table_name" > db/schema.txt

echo "db/schema.txt: 테이블 $(wc -l < db/schema.txt | tr -d ' ')개"
