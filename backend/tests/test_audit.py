"""감사 기록 테스트 (M6). 개인정보를 남기지 않는지(절대 규칙 6), 기록하지 못하면 닫히는지 본다."""

import json

import psycopg
import pytest
import yaml

from nlq import ExecutionError, execute
from nlq.audit import AuditError, mask_sql
from nlq.guard import GuardError
from nlq.models import Rows
from nlq.settings import ROOT, readonly_conninfo
from nlq.users import load_users

from conftest import execute_module

KIM = load_users()["sales.kim"].user
EVAL = ROOT / "eval"
FIELDS = {"ts", "uid", "enforce", "outcome", "sql", "rows", "truncated", "ms"}


def _db_available() -> bool:
    try:
        psycopg.connect(**readonly_conninfo(), connect_timeout=2).close()
        return True
    except (psycopg.Error, RuntimeError):
        return False


db = pytest.mark.skipif(not _db_available(), reason="nlq_readonly로 접속할 DB가 없다")


def _entries(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    ("sql", "masked"),
    [
        ("SELECT * FROM res_partner WHERE name = '김철수'", "SELECT * FROM res_partner WHERE name = '?'"),
        ("SELECT * FROM res_partner WHERE email LIKE '%kim@example.com%' AND id > 3",
         "SELECT * FROM res_partner WHERE email LIKE '?' AND id > 3"),
        ("SELECT 1 /* 김철수 */ -- 010-1234-5678", "SELECT 1"),
        ("SELECT name->>'ko_KR' FROM res_partner", "SELECT name ->> '?' FROM res_partner"),
        ("SELECT $$김철수$$", "SELECT '?'"),
        ("SELECT E'\\x41'", "SELECT '?'"),
    ],
)
def test_mask_sql_hides_string_literals(sql, masked):
    assert mask_sql(sql) == masked


def test_unparsable_sql_is_not_recorded():
    assert mask_sql("SELECT FROM WHERE '김철수'") is None
    assert mask_sql("") is None


def test_guard_rejection_is_recorded_without_literals(audit_log):
    with pytest.raises(GuardError):
        execute("SELECT * FROM pg_roles WHERE rolname = '김철수'", KIM)
    [entry] = _entries(audit_log)
    assert set(entry) == FIELDS
    assert entry["uid"] == 7 and entry["outcome"] == "guard_rejected" and entry["rows"] is None
    assert "김철수" not in audit_log.read_text()
    assert "sales.kim" not in audit_log.read_text()  # login 대신 uid


def test_failed_parse_is_recorded_without_sql(audit_log):
    with pytest.raises(GuardError):
        execute("SELECT FROM WHERE '김철수'", KIM)
    [entry] = _entries(audit_log)
    assert entry["sql"] is None
    assert "김철수" not in audit_log.read_text()


def test_timeout_is_classified(monkeypatch, audit_log):
    def slow(sql, user, mode):
        try:
            raise psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
        except psycopg.Error as e:
            raise ExecutionError("시간 제한") from e

    monkeypatch.setattr(execute_module, "_execute", slow)
    with pytest.raises(ExecutionError):
        execute("SELECT 1", KIM)
    assert _entries(audit_log)[0]["outcome"] == "timeout"


def test_unwritable_log_fails_closed(monkeypatch, tmp_path):
    # 기록을 남기지 못하면 결과 대신 오류가 나간다
    monkeypatch.setenv("NLQ_AUDIT_LOG", str(tmp_path))  # 디렉터리라 열 수 없다
    rows = Rows(columns=["x"], rows=[(1,)], executed_sql="SELECT 1")
    monkeypatch.setattr(execute_module, "_execute", lambda sql, user, mode: rows)
    with pytest.raises(AuditError):
        execute("SELECT 1", KIM)


@pytest.mark.parametrize("path", sorted(EVAL.glob("*/*.yaml")), ids=lambda p: p.stem)
def test_every_eval_sql_is_recorded(path):
    # 가리기가 실제 쿼리를 통째로 버리지 않는지. 평가·예시 SQL은 모두 기록돼야 한다
    item = yaml.safe_load(path.read_text())
    sql = item.get("gold_sql") or item.get("sql")
    if sql:
        assert mask_sql(sql)


@db
@pytest.mark.usefixtures("enforce")
def test_success_is_recorded_without_values(audit_log):
    rows = execute("SELECT name FROM res_partner WHERE name ILIKE '%furniture%'", KIM)
    names = [r[0] for r in rows.rows]
    assert names
    [entry] = _entries(audit_log)
    assert entry["outcome"] == "ok" and entry["rows"] == len(names)
    assert "furniture" not in audit_log.read_text().lower()
    assert not any(n in audit_log.read_text() for n in names)


@db
def test_db_error_message_is_not_recorded(audit_log):
    # DB 오류 첫 줄에는 행의 값이 섞인다(형 변환 실패한 이름). 종류만 남긴다
    with pytest.raises(ExecutionError) as e:
        execute("SELECT name::int FROM res_company", KIM)
    [entry] = _entries(audit_log)
    assert entry["outcome"] == "error"
    message = str(e.value)
    assert '"' in message  # 오류 문구에 값이 들어 있다
    assert message.split('"')[1] not in audit_log.read_text()
