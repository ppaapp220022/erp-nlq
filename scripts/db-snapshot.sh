#!/usr/bin/env bash
# Odoo DB 스냅숏을 저장하거나 복원한다. 평가가 같은 데이터 위에서 돌도록 고정하는 용도다.
#   ./scripts/db-snapshot.sh save [파일이름]     snapshots/ 아래에 zip(DB + filestore) 저장
#   ./scripts/db-snapshot.sh restore <파일이름>  기존 DB를 지우고 스냅숏으로 되돌림
# Odoo의 `db dump/load`를 써서 filestore까지 함께 다룬다.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

: "${ODOO_DB_NAME:?.env에 ODOO_DB_NAME을 넣어 주세요}"
mkdir -p snapshots

odoo_db() {
  docker compose run --rm --no-deps -T --entrypoint odoo \
    -v "$PWD/snapshots:/snapshots" odoo \
    db --db_host db -r odoo -w "${ODOO_DB_PASSWORD:-odoo}" "$@"
}

case "${1:-}" in
  save)
    name="${2:-$ODOO_DB_NAME-$(date +%Y%m%d).zip}"
    odoo_db dump "$ODOO_DB_NAME" "/snapshots/$name"
    echo "저장: snapshots/$name"
    ;;
  restore)
    name="${2:?복원할 파일 이름을 주세요 (snapshots/ 안)}"
    name="$(basename "$name")"
    [[ -f "snapshots/$name" ]] || { echo "snapshots/$name 없음" >&2; exit 1; }
    # 실행 중인 Odoo가 DB 연결을 잡고 있으면 지울 수 없어서 잠시 멈춘다.
    docker compose stop odoo
    # --move: DB UUID를 그대로 둔다. 스냅숏과 완전히 같은 상태로 되돌리기 위해서다.
    odoo_db load --force --move "$ODOO_DB_NAME" "/snapshots/$name"
    docker compose start odoo
    # 역할 권한과 PUBLIC 권한 회수를 다시 맞춘다.
    ./scripts/db-readonly-role.sh
    echo "복원: snapshots/$name → $ODOO_DB_NAME"
    ;;
  *)
    sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
