"""Odoo 보고서 대조 (nlq/report_check.py).

정의 SQL을 사용자마다 execute()한 합계가 Odoo 보고서(eval/odoo_reports.toml, scripts/odoo_report_totals.py로 생성)와
같은지 본다. 행 수(test_odoo_scope.py)에 더해 금액 합계까지 권한 범위가 Odoo와 같다는 회귀 테스트다.
시스템 답(Claude API) 대조는 nlq-report로 돌리고 여기서는 부르지 않는다.
"""

from pathlib import Path

import psycopg
import pytest

from nlq import report_check
from nlq.ask import Attempt
from nlq.models import Clarification, Rows
from nlq.settings import readonly_conninfo
from nlq.users import load_users

REPORTS = report_check.load_odoo_reports()
CASES = [(login, metric) for login, metrics in REPORTS.items() for metric in metrics]


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


def test_reports_cover_known_users_and_metrics():
    assert set(REPORTS) <= set(load_users())
    assert {m for metrics in REPORTS.values() for m in metrics} <= set(report_check.METRICS)
    # 관리자와 영업 사원(범위가 좁은 역할)이 모두 있어야 권한까지 대조된다
    assert "admin" in REPORTS and "sales.kim" in REPORTS


@db
@pytest.mark.parametrize(("login", "metric"), CASES, ids=[f"{l}-{m}" for l, m in CASES])
def test_definition_matches_odoo_report(login, metric):
    check = report_check.check_definition(login, metric, REPORTS[login][metric])
    assert check.definition == check.odoo


def _check():
    return report_check.Check(login="admin", metric="receivable", odoo={"A": report_check.normalize(10)})


def test_answer_compares_like_eval(monkeypatch):
    rows = Rows(columns=["company_name", "total"], rows=[("A", 10.0)], executed_sql="")
    monkeypatch.setattr(report_check, "ask", lambda q, user: [Attempt(sql="SELECT 1", model="m", rows=rows)])
    assert report_check.check_answer(_check()).answer == "correct"
    wrong = Rows(columns=["c", "t"], rows=[("A", 11)], executed_sql="")
    monkeypatch.setattr(report_check, "ask", lambda q, user: [Attempt(sql="SELECT 1", model="m", rows=wrong)])
    assert report_check.check_answer(_check()).answer == "wrong"


def test_clarification_is_not_an_answer(monkeypatch):
    c = Clarification("어느 쪽?", ("a", "b"))
    monkeypatch.setattr(report_check, "ask", lambda q, user: [Attempt(sql="", model="m", clarification=c)])
    assert report_check.check_answer(_check()).answer == "clarification"


def test_report_check_reaches_db_only_through_execute_and_ask():
    source = Path(report_check.__file__).read_text()
    assert "psycopg" not in source and "nlq.guard" not in source
