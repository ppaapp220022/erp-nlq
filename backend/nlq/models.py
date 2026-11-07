from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class User:
    """질문하는 사람. Odoo 사용자와 1:1이다.

    행 범위는 "담당자 조건 AND 회사 조건"이라 회사 목록도 신원의 일부다.
    groups(행 범위를 정하는 Odoo 그룹)와 tables(Odoo가 읽기를 허락한 테이블)는 eval/users.toml에서 온다.
    기본값이 비어 있어 아무것도 읽을 수 없다(실패 시 닫힘).
    """

    odoo_uid: int
    login: str
    company_ids: tuple[int, ...]
    groups: frozenset[str] = frozenset()
    tables: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Clarification:
    """질문이 업무 기준(주문/송장, 부가세, 환불) 중 하나에서 갈려 SQL 대신 되묻는 질문 (M5)."""

    question: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedSQL:
    """generate()의 결과. 신뢰하지 않는 값이다. execute()가 다시 검증한다."""

    sql: str
    model: str
    # 되묻기(M5)가 필요하면 sql은 빈 문자열이고 이것을 돌려준다.
    clarification: Clarification | None = None


@dataclass(frozen=True)
class Failed:
    """앞서 만든 SQL과 execute()가 낸 오류. 자기 수정(M5)이 generate()에 다시 넣는다."""

    sql: str
    error: str


class GenerationError(Exception):
    """generate()가 SQL을 만들지 못했다 (거절, 출력 한도 초과 등)."""


class ExecutionError(Exception):
    """execute()가 SQL을 실행하지 못했다. 메시지는 DB 오류의 첫 줄이고, 개인정보를 담지 않는다."""


class GuardError(ExecutionError):
    """guard가 SQL을 거부했다. 메시지는 거부 이유이고, 자기 수정(M5)이 LLM에 다시 넣는다."""


@dataclass(frozen=True)
class Rows:
    """execute()의 결과. guard가 재작성한 SQL을 함께 돌려준다(화면의 "SQL 보기"와 감사 로그용)."""

    columns: list[str]
    rows: list[tuple]
    executed_sql: str
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
