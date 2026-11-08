"""guard와 같은 행 범위를 Postgres RLS 정책으로 옮긴다 (M6 비교, docs/adr/0005-rls-vs-guard.md).

규칙은 nlq/identity.py 하나에서 온다. 이 모듈은 그 규칙을 정책 SQL로 바꿔 db/rls_policies.sql을 만든다.
    uv run --directory backend python -m nlq.rls > db/rls_policies.sql
파일이 규칙과 어긋나면 tests/test_rls.py가 실패한다.

guard는 사용자를 아는 상태에서 해당 그룹 규칙만 골라 끼운다. 정책은 사용자를 모르는 채 한 번 만들어 두므로,
Odoo의 합치기(`전역 AND (해당 그룹 규칙 OR ...)`, 해당 그룹이 없으면 전역만)를 식 안에서 한다.
    전역 AND (어느 그룹에도 없음 OR (그룹1 AND 조건1) OR (그룹2 AND 조건2) ...)
Odoo ACL(테이블 읽기 권한)도 `nlq.can_read`로 함께 건다. 사용자 문맥 함수는 db/rls_context.sql에 있다.
"""

from __future__ import annotations

from nlq.identity import TABLES

CONTEXT = {
    "uid": "nlq.uid()",
    "companies": "SELECT unnest(nlq.company_ids())",
    "parent_companies": "SELECT unnest(nlq.parent_company_ids())",
}

GUARD_POLICY = "nlq_guard"  # nlq_readonly: 행 범위는 guard가 재작성으로 건다
RLS_POLICY = "nlq_rls"  # nlq_rls: 행 범위를 정책이 건다

HEADER = """\
-- 생성 파일. 직접 고치지 않는다: uv run --directory backend python -m nlq.rls > db/rls_policies.sql
-- 규칙은 backend/nlq/identity.py, 사용자 문맥 함수는 db/rls_context.sql 에 있다.
-- scripts/db-readonly-role.sh 가 psql 변수 ro_user, rls_user 를 넘겨 실행한다.
--
-- RLS를 켜면 정책이 없는 역할은 행을 하나도 못 읽는다. 그래서 두 역할에 정책을 따로 둔다.
--   ro_user (nlq_readonly): guard가 SQL을 재작성해 범위를 거는 경로. 정책은 모든 행을 연다.
--   rls_user (nlq_rls):      guard 재작성 없이 정책이 범위를 거는 경로 (ADR 0005).
-- FORCE ROW LEVEL SECURITY는 쓰지 않는다. 소유자이자 superuser인 odoo(Odoo 서버)는 영향이 없다.

\\set ON_ERROR_STOP on
SET client_min_messages = warning;

BEGIN;
"""


def policy_condition(table: str) -> str:
    """테이블의 RLS USING 식. 사용자 값은 nlq.* 문맥 함수로 읽는다."""
    rule = TABLES[table]
    values = {**CONTEXT, "table": table}
    parts = [f"nlq.can_read('{table}')", rule.global_rule.format(**values)]
    if rule.group_rules:
        groups = [f"nlq.has_group('{group}')" for group, _ in rule.group_rules]
        none = "NOT (" + " OR ".join(groups) + ")"
        matched = [f"({g} AND {cond.format(**values)})" for g, (_, cond) in zip(groups, rule.group_rules)]
        parts.append("(" + " OR ".join([none, *matched]) + ")")
    return " AND ".join(parts)


def policies_sql() -> str:
    lines = [HEADER]
    for table in sorted(TABLES):
        lines += [
            f"-- {table}",
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;",
            f"DROP POLICY IF EXISTS {GUARD_POLICY} ON {table};",
            f'CREATE POLICY {GUARD_POLICY} ON {table} FOR SELECT TO :"ro_user" USING (true);',
            f"DROP POLICY IF EXISTS {RLS_POLICY} ON {table};",
            f'CREATE POLICY {RLS_POLICY} ON {table} FOR SELECT TO :"rls_user"',
            f"  USING ({policy_condition(table)});",
            "",
        ]
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(policies_sql(), end="")
