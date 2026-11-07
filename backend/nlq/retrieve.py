"""질문과 비슷한 예시(eval/examples/)를 골라 사용자 메시지에 넣는다 (M5 검색).

방식은 셋이다. NLQ_RETRIEVE로 고른다.
  none       예시를 넣지 않는다
  keyword    질문 글자 2-gram의 BM25 (기본. Haiku 3회 평균 OKF 포함 45.7 → 48.0/50, docs/plan.md "M5 검색 비교")
  embedding  다국어 문장 임베딩(fastembed)의 코사인 유사도

예시는 40개뿐이라 색인은 메모리에 둔다. pgvector는 쓰지 않는다(docs/adr/0004-example-retrieval-in-memory.md).
예시는 SQL이 쓰는 테이블을 모두 읽을 수 있는 사용자에게만 고른다. 프롬프트 거르기와 같이 정보 노출을 줄이는
장치이고 권한을 지키는 장치가 아니다. 평가 문항(eval/questions/)은 읽지 않는다(절대 규칙 4).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import sqlglot
import yaml
from sqlglot import exp

from nlq.identity import can_read
from nlq.models import User
from nlq.settings import ROOT, setting

EXAMPLES = ROOT / "eval" / "examples"
METHODS = ("none", "keyword", "embedding")
DEFAULT_METHOD = "keyword"
TOP_K = 3
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_CACHE = ROOT / ".cache" / "fastembed"
# BM25 기본값
K1 = 1.2
B = 0.75


@dataclass(frozen=True)
class Example:
    id: str
    question: str
    sql: str
    tables: frozenset[str]


def retrieve_method() -> str:
    method = setting("NLQ_RETRIEVE", DEFAULT_METHOD)
    if method not in METHODS:
        raise RuntimeError(f"NLQ_RETRIEVE는 {', '.join(METHODS)} 중 하나다: {method}")
    return method


def sql_tables(sql: str) -> frozenset[str]:
    # CTE 이름도 테이블로 센다. 읽을 수 없는 이름이 되어 예시가 빠질 뿐이다(실패 시 닫힘).
    return frozenset(t.name.lower() for t in sqlglot.parse_one(sql, dialect="postgres").find_all(exp.Table))


@cache
def load_examples(directory: Path = EXAMPLES) -> tuple[Example, ...]:
    examples = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        sql = data["sql"].strip()
        examples.append(Example(id=data["id"], question=data["question"].strip(), sql=sql, tables=sql_tables(sql)))
    return tuple(examples)


def readable_examples(user: User) -> list[Example]:
    return [e for e in load_examples() if all(can_read(t, user) for t in e.tables)]


def retrieve(question: str, user: User, method: str | None = None, k: int = TOP_K) -> list[Example]:
    """user가 읽을 수 있는 예시 중 question과 가까운 k개. 점수가 0인 예시는 고르지 않는다."""
    method = method or retrieve_method()
    if method == "none":
        return []
    candidates = readable_examples(user)
    if not candidates:
        return []
    scores = _keyword_scores(question, candidates) if method == "keyword" else _embedding_scores(question, candidates)
    ranked = sorted(zip(scores, range(len(candidates))), key=lambda x: (-x[0], x[1]))
    return [candidates[i] for score, i in ranked[:k] if score > 0]


def _bigrams(text: str) -> list[str]:
    # 한국어는 조사가 붙어 단어 단위로 맞지 않는다. 공백을 빼고 글자 2-gram으로 본다.
    s = re.sub(r"\s+", "", text.lower())
    return [s[i : i + 2] for i in range(len(s) - 1)]


def _keyword_scores(question: str, candidates: list[Example]) -> list[float]:
    docs = [Counter(_bigrams(e.question)) for e in candidates]
    avg_len = sum(sum(d.values()) for d in docs) / len(docs)
    df = Counter(g for d in docs for g in d)
    n = len(docs)
    scores = []
    for d in docs:
        length = sum(d.values())
        score = 0.0
        for g in set(_bigrams(question)):
            tf = d.get(g, 0)
            if tf:
                idf = math.log(1 + (n - df[g] + 0.5) / (df[g] + 0.5))
                score += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * length / avg_len))
        scores.append(score)
    return scores


@cache
def _model():
    from fastembed import TextEmbedding  # 처음 쓸 때만 불러온다(모델 적재에 수십 초)

    return TextEmbedding(EMBEDDING_MODEL, cache_dir=str(MODEL_CACHE))


@cache
def _example_vectors(questions: tuple[str, ...]):
    import numpy as np

    vectors = np.array(list(_model().embed(list(questions))))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def _embedding_scores(question: str, candidates: list[Example]) -> list[float]:
    import numpy as np

    vectors = _example_vectors(tuple(e.question for e in candidates))
    q = np.array(list(_model().embed([question])))[0]
    return [float(s) for s in vectors @ (q / np.linalg.norm(q))]
