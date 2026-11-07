"""채점 비교 규칙과 채점 실행 테스트. 비교 규칙은 DB 없이 돈다."""

from datetime import date, datetime
from decimal import Decimal

import psycopg
import pytest

from nlq import ask, evaluate
from nlq.models import GeneratedSQL, Rows
from nlq.scoring import matches
from nlq.settings import readonly_conninfo


def rows(columns, data, truncated=False):
    return Rows(columns=columns, rows=data, executed_sql="", truncated=truncated)


GOLD = rows(["name", "qty"], [("Chair", Decimal("27.00")), ("Lamp", Decimal("11.00"))])


def test_same_result():
    assert matches(GOLD, GOLD, order_matters=True)


def test_column_names_ignored():
    assert matches(GOLD, rows(["product", "total"], GOLD.rows), order_matters=True)


def test_rounding_and_int_decimal_ignored():
    assert matches(GOLD, rows(["n", "q"], [("Chair", 27), ("Lamp", 11.004)]), order_matters=True)


def test_extra_and_reordered_columns_allowed():
    pred = rows(["id", "qty", "name"], [(5, Decimal("27"), "Chair"), (6, Decimal("11"), "Lamp")])
    assert matches(GOLD, pred, order_matters=True)


def test_row_order():
    swapped = rows(GOLD.columns, list(reversed(GOLD.rows)))
    assert matches(GOLD, swapped, order_matters=False)
    assert not matches(GOLD, swapped, order_matters=True)


def test_missing_or_extra_rows_wrong():
    assert not matches(GOLD, rows(GOLD.columns, GOLD.rows[:1]), order_matters=False)
    assert not matches(GOLD, rows(GOLD.columns, GOLD.rows + [("Desk", 1)]), order_matters=False)


def test_values_must_stay_in_the_same_row():
    # 열마다 값 묶음은 같아도 행 안에서 짝이 바뀌면 틀리다
    pred = rows(GOLD.columns, [("Chair", Decimal("11")), ("Lamp", Decimal("27"))])
    assert not matches(GOLD, pred, order_matters=False)


def test_missing_column_wrong():
    assert not matches(GOLD, rows(["name"], [("Chair",), ("Lamp",)]), order_matters=False)


def test_truncated_is_wrong():
    assert not matches(GOLD, rows(GOLD.columns, GOLD.rows, truncated=True), order_matters=False)


def test_duplicate_rows_count():
    gold = rows(["x"], [(1,), (1,), (2,)])
    assert not matches(gold, rows(["x"], [(1,), (2,), (2,)]), order_matters=False)


def test_dates():
    gold = rows(["d"], [(date(2026, 11, 3),)])
    assert matches(gold, rows(["d"], [(datetime(2026, 11, 3),)]), order_matters=True)
    assert not matches(gold, rows(["d"], [(datetime(2026, 11, 3, 9, 30),)]), order_matters=True)


# --- 채점 실행 (DB 필요, API는 부르지 않는다) ---


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


def fake_generate(*sqls):
    """시도마다 sqls에서 하나씩 낸다. 마지막 것을 계속 낸다."""
    calls = []

    def generate(question, user, failed=None):
        calls.append(failed)
        return GeneratedSQL(sql=sqls[min(len(calls), len(sqls)) - 1], model="fake")

    generate.calls = calls
    return generate


@db
@pytest.mark.parametrize(
    ("sql", "status"),
    [
        (None, "correct"),  # 정답 SQL 그대로
        ("SELECT 1", "wrong"),
        ("SELECT * FROM pg_roles", "guard_rejected"),
        ("SELECT no_such_column FROM sale_order", "execution_error"),
    ],
)
def test_run_one(monkeypatch, sql, status):
    q = evaluate.load_questions(["stock-003"])[0]
    monkeypatch.setattr(ask, "generate", fake_generate(sql or q["gold_sql"]))
    assert evaluate.run_one(q, retries=0).status == status


@db
def test_run_one_retries_failed_sql(monkeypatch):
    # 자기 수정: 첫 SQL이 실패하면 오류를 넣어 한 번 다시 만들고, 마지막 시도를 채점한다
    q = evaluate.load_questions(["stock-003"])[0]
    fake = fake_generate("SELECT no_such_column FROM sale_order", q["gold_sql"])
    monkeypatch.setattr(ask, "generate", fake)
    result = evaluate.run_one(q)
    assert (result.status, result.retried) == ("correct", 1)
    assert "no_such_column" in result.first_error
    assert fake.calls[0] is None and "no_such_column" in fake.calls[1].error


@db
@pytest.mark.parametrize(
    ("sqls", "status", "calls"),
    [
        (("SELECT * FROM pg_roles",), "guard_rejected", 2),  # 다시 만들어도 실패하면 마지막 오류
        (("SELECT * FROM pg_roles",), "guard_rejected", 1),  # retries=0: 다시 만들지 않는다
        (("SELECT 1",), "wrong", 1),  # 실행은 됐으나 틀린 답은 다시 만들지 않는다
    ],
)
def test_run_one_retry_limits(monkeypatch, sqls, status, calls):
    q = evaluate.load_questions(["stock-003"])[0]
    fake = fake_generate(*sqls)
    monkeypatch.setattr(ask, "generate", fake)
    assert evaluate.run_one(q, retries=calls - 1).status == status
    assert len(fake.calls) == calls


def test_summary_table():
    results = [
        evaluate.Result(id="sales-001", area="판매", role="demo", status="correct"),
        evaluate.Result(id="sales-002", area="판매", role="demo", status="guard_rejected"),
        evaluate.Result(id="stock-001", area="재고", role="demo", status="wrong"),
        evaluate.Result(id="stock-002", area="재고", role="demo", status="correct", retried=1),
    ]
    table = evaluate.format_summary(evaluate.summarize(results))
    assert "| 판매 | 1 | 2 | 50% | 0 | 1 | 0 | 0 | 0 |" in table
    assert "| 재고 | 1 | 2 | 50% | 0 | 0 | 0 | 1 | 1 |" in table
    assert "| 전체 | 2 | 4 | 50% |" in table
