"""화면이 부르는 HTTP API (M4). generate()와 execute()를 감싸기만 한다.

    uv run --directory backend nlq-api      # 127.0.0.1:8000

엔드포인트는 셋이다(docs/architecture.md "함수 경계").
  GET  /users      고를 수 있는 사용자(login, 역할 이름)
  POST /generate   질문 → SQL. 결과는 신뢰하지 않는다. failed(앞 SQL과 오류)를 주면 고쳐 쓴다(자기 수정).
                   업무 기준이 갈리면 sql 대신 clarification(질문, 선택지)을 준다. 고른 기준은 clarified로 다시 보낸다(되묻기)
  POST /execute    SQL → 결과. 권한은 여기서 execute()가 강제한다

사용자는 화면의 역할 선택으로 정한다. 로그인이 없는 데모라서, 이 API는 127.0.0.1에만 연다.
질문·SQL·결과는 로그에 남기지 않는다(절대 규칙 6).
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from nlq import ExecutionError, Failed, GenerationError, execute, generate
from nlq.models import GuardError, User
from nlq.users import load_users

HOST = "127.0.0.1"
PORT = 8000
MAX_QUESTION = 1_000
MAX_SQL = 20_000
MAX_ERROR = 2_000
MAX_CLARIFIED = 300

app = FastAPI(title="erp-nlq", docs_url=None, redoc_url=None, openapi_url=None)


class FailedAttempt(BaseModel):
    sql: str = Field(min_length=1, max_length=MAX_SQL)
    error: str = Field(min_length=1, max_length=MAX_ERROR)


class GenerateRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)
    user: str
    failed: FailedAttempt | None = None
    clarified: str | None = Field(default=None, min_length=1, max_length=MAX_CLARIFIED)


class ExecuteRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=MAX_SQL)
    user: str


@app.get("/users")
def users() -> list[dict[str, str]]:
    return [{"login": login, "role": p.role} for login, p in load_users().items()]


@app.post("/generate")
def generate_sql(req: GenerateRequest) -> dict:
    try:
        failed = Failed(sql=req.failed.sql, error=req.failed.error) if req.failed else None
        generated = generate(req.question, _user(req.user), failed, req.clarified)
    except GenerationError as e:
        raise _error(502, "generation_error", str(e)) from e
    c = generated.clarification
    clarification = {"question": c.question, "options": list(c.options)} if c else None
    return {"sql": generated.sql, "model": generated.model, "clarification": clarification}


@app.post("/execute")
def execute_sql(req: ExecuteRequest) -> dict:
    try:
        rows = execute(req.sql, _user(req.user))
    except GuardError as e:
        raise _error(403, "guard_rejected", str(e)) from e
    except ExecutionError as e:
        raise _error(400, "execution_error", str(e)) from e
    return {
        "columns": rows.columns,
        "rows": [[_cell(v) for v in row] for row in rows.rows],
        "truncated": rows.truncated,
        "warnings": rows.warnings,
    }


def _user(login: str) -> User:
    persona = load_users().get(login)
    if persona is None:
        raise _error(400, "unknown_user", f"없는 사용자: {login}")
    return persona.user


def _error(status: int, kind: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"kind": kind, "message": message})


def _cell(value: object) -> str | int | float | bool | None:
    # 화면 표시용이다. 채점은 이 변환을 거치지 않는다(nlq/scoring.py).
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (bytes, memoryview)):
        return "(바이너리)"
    return str(value)


def main() -> int:
    import uvicorn

    print(f"nlq-api: http://{HOST}:{PORT}", file=sys.stderr)
    uvicorn.run(app, host=HOST, port=PORT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
