from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _dotenv() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and not key.lstrip().startswith("#"):
            values[key.strip()] = value.strip()
    return values


def setting(name: str, default: str | None = None) -> str | None:
    """환경 변수를 먼저 보고, 없으면 레포 루트의 .env를 본다."""
    return os.environ.get(name) or _dotenv().get(name) or default


ENFORCEMENTS = ("guard", "rls", "both")


def enforcement() -> str:
    """행 범위를 거는 방식 (M6 비교, ADR 0005). NLQ_ENFORCE, 기본은 guard.

    guard: guard가 SQL을 재작성해 건다. nlq_readonly로 접속한다.
    rls:   guard는 검증만 하고 RLS 정책이 건다. nlq_rls로 접속한다.
    both:  guard 재작성과 RLS 정책을 함께 건다. nlq_rls로 접속한다.
    """
    value = setting("NLQ_ENFORCE", "guard")
    if value not in ENFORCEMENTS:
        raise RuntimeError(f"NLQ_ENFORCE는 {'|'.join(ENFORCEMENTS)} 중 하나다: {value}")
    return value


def readonly_conninfo(rls: bool = False) -> dict[str, str]:
    """질의 계층의 DB 접속 정보. 계정은 nlq_readonly, RLS 경로에서는 nlq_rls뿐이다 (CLAUDE.md 절대 규칙 2)."""
    password = setting("NLQ_RO_PASSWORD")
    if not password:
        raise RuntimeError(".env에 NLQ_RO_PASSWORD가 없다")
    user = setting("NLQ_RO_USER", "nlq_readonly")
    if rls:
        user = setting("NLQ_RLS_USER", "nlq_rls")
        password = setting("NLQ_RLS_PASSWORD", password)
    return {
        "host": setting("NLQ_DB_HOST", "127.0.0.1"),
        "port": setting("NLQ_DB_PORT", "5432"),
        "dbname": setting("ODOO_DB_NAME", "erp"),
        "user": user,
        "password": password,
    }


def eval_today() -> str:
    """"오늘"로 쓸 날짜. 데모 데이터가 스냅숏에 묶여 있어서 실제 오늘 대신 고정값을 쓴다 (eval/README.md)."""
    text = (ROOT / "eval" / "config.yaml").read_text()
    match = re.search(r"^today:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    if not match:
        raise RuntimeError("eval/config.yaml에 today가 없다")
    return match.group(1)
