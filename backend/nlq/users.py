from __future__ import annotations

import tomllib
from dataclasses import dataclass

from nlq.models import User
from nlq.settings import ROOT

USERS_FILE = ROOT / "eval" / "users.toml"  # scripts/odoo_users.py 로 생성


@dataclass(frozen=True)
class Persona:
    """화면·CLI·평가에서 고르는 사용자. 역할 이름은 보여 주기용이고 권한 판단에는 쓰지 않는다."""

    user: User
    role: str


def load_users() -> dict[str, Persona]:
    data = tomllib.loads(USERS_FILE.read_text())
    return {
        login: Persona(
            user=User(
                odoo_uid=entry["uid"],
                login=login,
                company_ids=tuple(entry["companies"]),
                groups=frozenset(entry["groups"]),
                tables=frozenset(entry["tables"]),
            ),
            role=entry["role"],
        )
        for login, entry in data["users"].items()
    }
