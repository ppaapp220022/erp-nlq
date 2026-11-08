"""CI 평가(eval/ci/)의 문항 목록과 축소 덤프 검사 (M6). DB 없이 돈다."""

import gzip
import re

import yaml

from nlq.identity import TABLES
from nlq.settings import ROOT

CI = ROOT / "eval" / "ci"
QUESTIONS = {p.stem: yaml.safe_load(p.read_text()) for p in (ROOT / "eval" / "questions").glob("*.yaml")}


def test_ci_questions_are_five_per_area():
    ci = yaml.safe_load((CI / "questions.yaml").read_text())
    ids = ci["questions"]
    assert len(ids) == len(set(ids)) == 20
    assert set(ids) <= set(QUESTIONS)
    areas = [QUESTIONS[i]["area"] for i in ids]
    assert {a: areas.count(a) for a in set(areas)} == {"판매": 5, "구매": 5, "재고": 5, "회계": 5}
    assert 0 < ci["min_correct"] <= len(ids)


def _dump() -> str:
    return gzip.decompress((CI / "erp-ci.sql.gz").read_bytes()).decode()


def test_dump_has_only_allowed_tables():
    tables = set(re.findall(r"^CREATE TABLE public\.(\w+) \(", _dump(), re.M))
    assert tables == set(TABLES)


def test_dump_has_no_user_secrets():
    # res_users는 질의 계층에 열린 열만 담는다. 비밀번호·서명·2단계 인증 값이 레포에 올라가지 않는다
    dump = _dump()
    columns = re.search(r"^COPY public\.res_users \((.*)\) FROM stdin;", dump, re.M).group(1)
    assert columns == "id, partner_id, company_id, active, share"
    assert not re.search(r"\$pbkdf2", dump)


def test_dump_has_no_portal_tokens():
    # 포털 공유 링크 토큰은 비운다. COPY 데이터에서 access_token 열이 모두 \N이어야 한다
    lines = _dump().splitlines()
    for table in ("sale_order", "purchase_order", "account_move"):
        start = next(i for i, line in enumerate(lines) if line.startswith(f"COPY public.{table} ("))
        columns = re.match(r"COPY \S+ \((.*)\) FROM stdin;", lines[start]).group(1).split(", ")
        rows = [line.split("\t") for line in lines[start + 1 : lines.index("\\.", start)]]
        assert rows and all(len(row) == len(columns) for row in rows), table
        index = columns.index("access_token")
        assert all(row[index] == r"\N" for row in rows), table


# Odoo 데모 데이터가 쓰는 예약·가짜 도메인. 실제 주소가 섞이면 덤프를 다시 봐야 한다
DEMO_EMAIL = re.compile(r"@([\w.-]+\.)?(example\.com|yourcompany\.com|fake\.[\w.-]+)$", re.I)
# scripts/seed_salespeople.py가 만든 가상의 영업 사원. 이메일·전화가 없다
SEED_NAMES = {"김민준", "이서연", "박지훈", "최윤서"}


def test_dump_partners_are_demo_data():
    # 덤프는 공개 레포에 올라간다. 거래처 연락처는 Odoo 데모의 가짜 주소이거나 비어 있어야 한다
    lines = _dump().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("COPY public.res_partner ("))
    columns = re.match(r"COPY \S+ \((.*)\) FROM stdin;", lines[start]).group(1).split(", ")
    rows = [dict(zip(columns, line.split("\t"))) for line in lines[start + 1 : lines.index("\\.", start)]]
    assert rows
    for row in rows:
        email = row["email"]
        assert email == r"\N" or DEMO_EMAIL.search(email), email
        if email == r"\N" and row["name"] in SEED_NAMES:
            assert row["phone"] == r"\N"
