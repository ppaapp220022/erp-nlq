"""예시 검색 (nlq/retrieve.py). 역할로 거르는지, 방식별로 가까운 예시를 고르는지, 생성 요청에 들어가는지 본다.

임베딩 검색은 모델 파일(.cache/fastembed)이 있을 때만 돈다. 처음 받는 데 수십 초가 걸려 CI에서는 건너뛴다.
"""

import pytest

from nlq import generate
from nlq.identity import TABLES, can_read
from nlq.prompt import user_message
from nlq.retrieve import MODEL_CACHE, load_examples, readable_examples, retrieve, retrieve_method, sql_tables
from nlq.users import load_users

from test_generate import _fake_client

PERSONAS = load_users()
EXAMPLES = load_examples()
embedding = pytest.mark.skipif(not MODEL_CACHE.exists(), reason="임베딩 모델 파일이 없다 (.cache/fastembed)")


def test_examples_come_from_examples_folder_only():
    # 절대 규칙 4: 평가 문항(id가 ex-로 시작하지 않는다)은 검색 대상이 아니다
    assert len(EXAMPLES) >= 40
    assert all(e.id.startswith("ex-") for e in EXAMPLES)


def test_sql_tables():
    sql = "SELECT 1 FROM sale_order o JOIN res_partner p ON p.id = o.partner_id WHERE o.id IN (SELECT order_id FROM sale_order_line)"
    assert sql_tables(sql) == {"sale_order", "res_partner", "sale_order_line"}


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda e: e.id)
def test_example_tables_are_known(example):
    # 예시가 허용 목록 밖 테이블을 쓰면 아무 사용자에게도 고를 수 없고, guard도 거부한다
    assert example.tables and example.tables <= TABLES.keys()


@pytest.mark.parametrize("login", sorted(PERSONAS))
def test_readable_examples_use_only_readable_tables(login):
    user = PERSONAS[login].user
    readable = readable_examples(user)
    assert all(can_read(t, user) for e in readable for t in e.tables)
    # 읽을 수 없는 테이블을 쓰는 예시는 모두 빠진다
    left_out = set(EXAMPLES) - set(readable)
    assert all(any(not can_read(t, user) for t in e.tables) for e in left_out)


def test_stock_user_never_gets_customer_invoice_examples():
    # 재고 담당(account_move 못 읽음)에게 회계 예시를 보여 주지 않는다. 질문이 회계를 물어도 같다
    choi = PERSONAS["stock.choi"].user
    for method in ("keyword", "embedding") if MODEL_CACHE.exists() else ("keyword",):
        found = retrieve("회사별 고객 송장 한 건의 평균 금액", choi, method=method, k=40)
        assert found and all("account_move" not in e.tables for e in found)


def test_none_returns_nothing():
    assert retrieve("회사별 미수금 총액", PERSONAS["admin"].user, method="none") == []


def test_retrieve_method_setting(monkeypatch):
    monkeypatch.delenv("NLQ_RETRIEVE", raising=False)
    monkeypatch.setenv("NLQ_RETRIEVE", "keyword")
    assert retrieve_method() == "keyword"
    monkeypatch.setenv("NLQ_RETRIEVE", "vector")
    with pytest.raises(RuntimeError, match="NLQ_RETRIEVE"):
        retrieve_method()


def test_keyword_finds_same_question_first():
    admin = PERSONAS["admin"].user
    for e in EXAMPLES:
        assert retrieve(e.question, admin, method="keyword")[0] == e


def test_keyword_returns_at_most_k_and_skips_zero_scores():
    admin = PERSONAS["admin"].user
    assert len(retrieve("회사별 미수금 총액", admin, method="keyword", k=3)) == 3
    assert retrieve("xyz", admin, method="keyword") == []


@embedding
def test_embedding_finds_same_question_first():
    admin = PERSONAS["admin"].user
    for e in EXAMPLES:
        assert retrieve(e.question, admin, method="embedding")[0] == e


def test_user_message_with_examples():
    admin = PERSONAS["admin"].user
    examples = list(EXAMPLES[:2])
    message = user_message("질문", admin, examples=examples)
    assert all(e.sql in message and e.question in message for e in examples)
    assert message.endswith("질문: 질문")
    # 예시가 없으면 이전과 같은 메시지다
    assert user_message("질문", admin) == f"질문한 사용자: res_users.id = {admin.odoo_uid}\n\n질문: 질문"


def test_generate_puts_examples_in_user_message_not_system(monkeypatch):
    # 시스템 프롬프트는 질문과 상관없이 같아야 캐시된다
    monkeypatch.setenv("NLQ_RETRIEVE", "keyword")
    calls = _fake_client(monkeypatch)
    choi = PERSONAS["stock.choi"].user
    generate("창고 재고가 가장 많은 품목", choi)
    expected = retrieve("창고 재고가 가장 많은 품목", choi, method="keyword")
    content = calls[0]["messages"][0]["content"]
    assert expected and all(e.sql in content for e in expected)
    assert "<examples>" not in calls[0]["system"][0]["text"]
