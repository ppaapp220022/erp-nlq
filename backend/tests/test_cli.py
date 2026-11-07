"""CLI 테스트. generate()·execute()는 가짜로 바꿔 API와 DB 없이 돈다."""

from decimal import Decimal

import pytest

from nlq import ExecutionError, GeneratedSQL, Rows, ask, cli
from nlq.users import load_users


def _rows(**kwargs):
    defaults = dict(columns=["name", "total"], rows=[("김민준", Decimal("1234.5")), (None, Decimal("0"))], executed_sql="SELECT 1")
    return Rows(**{**defaults, **kwargs})


def test_users_file_has_each_role_once_per_login():
    users = load_users()
    assert {p.role for p in users.values()} >= {"영업 사원", "재고 담당"}
    assert len({p.user.odoo_uid for p in users.values()}) == len(users)
    assert cli.DEFAULT_USER in users


def test_format_table_aligns_korean_and_marks_null():
    lines = cli.format_table(_rows()).splitlines()
    # 한글 이름(글자 3개, 화면 폭 6)과 머리글의 구분선이 같은 칸에 온다
    assert cli._width(lines[0].split("|")[0]) == cli._width(lines[2].split("|")[0])
    assert "1,234.5" in lines[2]
    assert "NULL" in lines[3]
    assert lines[-1] == "(2행)"


def test_format_table_reports_truncation():
    assert "잘림" in cli.format_table(_rows(truncated=True))


def test_question_goes_through_generate_and_execute(monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(ask, "generate", lambda q, user, failed: seen.setdefault("gen", (q, user)) and GeneratedSQL("SELECT 1", "m"))
    monkeypatch.setattr(ask, "execute", lambda sql, user: seen.setdefault("exec", (sql, user)) and _rows())
    assert cli.main(["매출", "--user", "stock.choi"]) == 0
    assert seen["gen"][0] == "매출"
    assert seen["gen"][1] == seen["exec"][1] == load_users()["stock.choi"].user
    assert "SELECT 1" in capsys.readouterr().out


def test_sql_option_skips_generate(monkeypatch):
    monkeypatch.setattr(cli, "generate", lambda *_: pytest.fail("생성하면 안 된다"))
    monkeypatch.setattr(cli, "execute", lambda sql, user: _rows())
    assert cli.main(["--sql", "SELECT 1"]) == 0


def test_execution_error_returns_1(monkeypatch, capsys):
    def fail(sql, user):
        raise ExecutionError("relation \"foo\" does not exist")

    monkeypatch.setattr(cli, "execute", fail)
    assert cli.main(["--sql", "SELECT * FROM foo"]) == 1
    assert "실행 실패" in capsys.readouterr().err


def test_unknown_user_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["질문", "--user", "nobody"])


def test_failed_sql_is_regenerated_once(monkeypatch, capsys):
    # 자기 수정: 첫 SQL이 실패하면 오류를 넣어 다시 만들고, 그 결과를 보여 준다
    calls = []

    def fake_generate(q, user, failed):
        calls.append(failed)
        return GeneratedSQL("SELECT bad" if failed is None else "SELECT 1", "m")

    def fake_execute(sql, user):
        if sql == "SELECT bad":
            raise ExecutionError('column "bad" does not exist')
        return _rows()

    monkeypatch.setattr(ask, "generate", fake_generate)
    monkeypatch.setattr(ask, "execute", fake_execute)
    assert cli.main(["매출"]) == 0
    assert calls[0] is None and calls[1].sql == "SELECT bad" and "bad" in calls[1].error
    out, err = capsys.readouterr()
    assert "SELECT bad" in out and "다시 만들었다" in err and "(2행)" in out
