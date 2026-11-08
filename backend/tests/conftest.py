"""여러 테스트 파일이 함께 쓰는 fixture."""

import importlib
import os

import psycopg
import pytest

from nlq.settings import readonly_conninfo

# nlq 패키지가 execute 함수를 같은 이름으로 내보내므로 모듈은 따로 가져온다.
execute_module = importlib.import_module("nlq.execute")

def pytest_sessionstart(session):
    """NLQ_REQUIRE_DB=1(CI)이면 두 역할로 접속되지 않을 때 테스트를 시작하지 않는다.

    DB 테스트는 접속이 안 되면 건너뛴다. CI에서 조용히 건너뛰어 통과하는 일을 막는다.
    """
    if os.environ.get("NLQ_REQUIRE_DB") != "1":
        return
    for rls in (False, True):
        try:
            psycopg.connect(**readonly_conninfo(rls), connect_timeout=5).close()
        except (psycopg.Error, RuntimeError) as e:
            raise pytest.UsageError(f"NLQ_REQUIRE_DB=1인데 DB에 접속하지 못했다 (rls={rls}): {type(e).__name__}") from e


# 행 범위를 거는 방식 (ADR 0005). rls_no_guard는 guard를 통째로 끄고 RLS 정책만 남긴다.
# guard가 뚫려도 정책이 막는지 본다.
ENFORCEMENTS = ["guard", "rls", "both", "rls_no_guard"]


@pytest.fixture(params=ENFORCEMENTS)
def enforce(request, monkeypatch):
    """권한 테스트를 방식마다 한 번씩 돌린다. 같은 SQL이 어느 방식에서도 권한 밖 행을 내지 않아야 한다."""
    mode = request.param
    if mode == "rls_no_guard":
        _rls_without_guard(monkeypatch)
    else:
        monkeypatch.setenv("NLQ_ENFORCE", mode)
    return mode


@pytest.fixture
def rls_no_guard(monkeypatch):
    """guard를 통째로 끄고 RLS 정책만 남긴다."""
    _rls_without_guard(monkeypatch)


def _rls_without_guard(monkeypatch):
    monkeypatch.setenv("NLQ_ENFORCE", "rls")
    monkeypatch.setattr(execute_module, "guard", lambda sql, user, max_rows, scope_rows: sql)
