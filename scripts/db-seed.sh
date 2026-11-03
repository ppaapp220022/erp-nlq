#!/usr/bin/env bash
# 데모 DB에 영업 사원을 더하고 주문·송장 담당자를 나눈다 (scripts/seed_salespeople.py).
# 마지막에 사용자별로 Odoo가 보여 주는 수와 SQL로 센 수를 나란히 출력한다.
exec "$(dirname "$0")/odoo-shell.sh" "$(dirname "$0")/seed_salespeople.py"
