from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class User:
    """질문하는 사람. Odoo 사용자와 1:1이다.

    행 범위는 "담당자 조건 AND 회사 조건"이라 회사 목록도 신원의 일부다.
    """

    odoo_uid: int
    login: str
    company_ids: tuple[int, ...]


@dataclass(frozen=True)
class GeneratedSQL:
    """generate()의 결과. 신뢰하지 않는 값이다. execute()가 다시 검증한다."""

    sql: str
    model: str
    # 되묻기(M5)가 필요하면 sql 대신 질문을 돌려준다.
    clarification: str | None = None


@dataclass(frozen=True)
class Rows:
    """execute()의 결과. guard가 재작성한 SQL을 함께 돌려준다(화면의 "SQL 보기"와 감사 로그용)."""

    columns: list[str]
    rows: list[tuple]
    executed_sql: str
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
