"""guard의 행 범위가 Odoo와 같은지 본다 (M3 "Odoo 권한 일치").

기준은 scripts/odoo_counts.py가 Odoo ORM으로 센 행 수(odoo_counts.toml)다. 사용자마다 허용 테이블 전부를
`SELECT count(*)`로 세어 같아야 한다. Odoo가 읽기 권한을 주지 않는 테이블은 guard가 막아야 한다.
로컬 DB(nlq_readonly)가 있어야 돈다. 스냅숏이나 그룹을 바꾸면 odoo_counts.toml을 다시 뽑는다.
"""

import tomllib
from pathlib import Path

import psycopg
import pytest

from nlq import execute
from nlq.guard import GuardError
from nlq.identity import TABLES
from nlq.settings import readonly_conninfo
from nlq.users import load_users

COUNTS = tomllib.loads((Path(__file__).parent / "odoo_counts.toml").read_text())["counts"]
USERS = {login: p.user for login, p in load_users().items()}


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")

CASES = [(login, table) for login in USERS for table in sorted(TABLES)]


def test_every_user_has_odoo_counts():
    assert set(USERS) <= set(COUNTS)


@pytest.mark.parametrize(("login", "table"), CASES, ids=[f"{u}-{t}" for u, t in CASES])
def test_row_count_matches_odoo(login, table, enforce):
    # 행 범위를 거는 방식(guard, RLS, 둘 다, guard 없이 RLS만)마다 Odoo와 같아야 한다 (ADR 0005)
    sql = f"SELECT count(*) FROM {table}"
    expected = COUNTS[login].get(table)
    if expected is None and enforce == "rls_no_guard":
        # guard가 없으면 테이블을 거부하는 대신 정책(nlq.can_read)이 행을 하나도 내주지 않는다
        assert execute(sql, USERS[login]).rows[0][0] == 0
    elif expected is None:
        with pytest.raises(GuardError):
            execute(sql, USERS[login])
    else:
        assert execute(sql, USERS[login]).rows[0][0] == expected
