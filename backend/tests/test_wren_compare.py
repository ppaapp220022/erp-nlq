"""비교 기준 2 러너 (nlq/wren_compare.py). WrenAI 없이 도는 부분만 본다: 넣는 내용, SQL 변환, 결과 형 맞추기.

WrenAI에 실제로 묻는 경로는 docker가 떠 있어야 해서 테스트하지 않는다(docs/reference/wrenai.md).
"""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from nlq import wren_compare
from nlq.wren_compare import INSTRUCTION_MAX, _chunks, _drop_catalog, _typed, instructions, relations, to_wren_sql


def test_does_not_touch_db_or_guard_directly():
    # 우리 쪽 실행은 execute() 하나로만 한다. WrenAI는 HTTP로만 부른다
    source = Path(wren_compare.__file__).read_text()
    assert "psycopg" not in source and "nlq.guard" not in source
    assert "from nlq import execute" in source


def test_instructions_come_from_knowledge_only():
    rules = instructions()
    assert all(len(r) <= INSTRUCTION_MAX for r in rules)
    assert any("2026-11-03" in r for r in rules)
    # 평가 문항(eval/questions/)의 질문 문장이 지침에 들어가지 않는다 (절대 규칙 4)
    import yaml

    root = Path(wren_compare.ROOT)
    questions = [yaml.safe_load(p.read_text())["question"] for p in (root / "eval" / "questions").glob("*.yaml")]
    text = "\n".join(rules)
    assert questions and not any(q in text for q in questions)


def test_chunks_respect_limit():
    text = "\n\n".join(["가" * 400] * 5 + ["나" * 2500])
    chunks = _chunks(text, limit=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks) == text.replace("\n", "")


def test_to_wren_sql_renames_tables_and_keeps_column_refs():
    sql = to_wren_sql("SELECT sale_order.name, p.name FROM sale_order JOIN res_partner p ON p.id = sale_order.partner_id")
    assert "public_sale_order AS sale_order" in sql
    assert "public_res_partner AS p" in sql


def test_to_wren_sql_leaves_cte_names():
    sql = to_wren_sql("WITH sale_order AS (SELECT 1 AS id) SELECT id FROM sale_order")
    assert "public_sale_order" not in sql


def test_drop_catalog_only_for_this_database():
    sql = _drop_catalog('SELECT id FROM erp."public".sale_order AS s JOIN other."public".x AS y ON 1 = 1')
    assert 'FROM "public".sale_order' in sql
    assert 'other."public".x' in sql


def test_relations_from_knowledge_arrows():
    models = {
        "public_sale_order": {"id": 1, "fields": {"id": 10, "partner_id": 11, "user_id": 12}},
        "public_res_partner": {"id": 2, "fields": {"id": 20}},
        "public_res_users": {"id": 3, "fields": {"id": 30}},
    }
    found = {(r["fromColumnId"], r["toColumnId"]) for r in relations(models)}
    assert (11, 20) in found and (12, 30) in found


def test_typed_restores_column_types():
    assert _typed("12.50", "DECIMAL128(38, 2)") == Decimal("12.50")
    assert _typed("2026-10-01", "DATE") == date(2026, 10, 1)
    assert _typed("2026-10-01 10:00:00.000000", "TIMESTAMP") == datetime(2026, 10, 1, 10)
    assert _typed("S00001", "VARCHAR") == "S00001"
    assert _typed(3, "INT64") == 3


def test_json_text_matches_wren_string():
    from nlq.models import Rows
    from nlq.wren_compare import _json_text

    rows = _json_text(Rows(columns=["name"], rows=[({"en_US": "Large Desk"},)], executed_sql=""))
    assert rows.rows == [('{"en_US": "Large Desk"}',)]
    assert _typed("2026-09-24", "date32[day]") == date(2026, 9, 24)
