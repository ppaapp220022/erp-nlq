from __future__ import annotations

import os
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


def readonly_conninfo() -> dict[str, str]:
    """질의 계층의 DB 접속 정보. 계정은 nlq_readonly뿐이다 (CLAUDE.md 절대 규칙 2)."""
    password = setting("NLQ_RO_PASSWORD")
    if not password:
        raise RuntimeError(".env에 NLQ_RO_PASSWORD가 없다")
    return {
        "host": setting("NLQ_DB_HOST", "127.0.0.1"),
        "port": setting("NLQ_DB_PORT", "5432"),
        "dbname": setting("ODOO_DB_NAME", "erp"),
        "user": setting("NLQ_RO_USER", "nlq_readonly"),
        "password": password,
    }
