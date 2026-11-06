"""평가 채점: 정답 SQL과 생성 SQL의 실행 결과를 비교한다 (eval/README.md "문항 형식").

- 열 이름은 무시한다. 생성 결과에 열이 더 있어도 정답 열이 모두 들어 있으면 맞다.
- 숫자는 소수 둘째 자리로 맞춘다. 정수와 소수(5와 5.00)는 같다.
- order_matters가 false면 행 순서도 무시한다. 행 수는 같아야 한다.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import product

from nlq.models import Rows

MAX_MAPPINGS = 10_000  # 정답 열 → 생성 열 대응을 이 수까지만 시도한다


def normalize(value: object) -> object:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, timedelta):
        return Decimal(str(value.total_seconds())).quantize(Decimal("0.01"))
    if isinstance(value, str):
        return value.strip()
    return str(value)


def matches(gold: Rows, pred: Rows, order_matters: bool) -> bool:
    """생성 결과가 정답과 같은지. 잘린 결과(행 수 제한)는 비교할 수 없어 틀린 것으로 본다."""
    if gold.truncated or pred.truncated or len(gold.rows) != len(pred.rows):
        return False
    if not gold.columns:
        return not pred.columns
    g = [tuple(normalize(v) for v in row) for row in gold.rows]
    p = [tuple(normalize(v) for v in row) for row in pred.rows]
    for mapping in _mappings(g, p, len(gold.columns), len(pred.columns)):
        projected = [tuple(row[k] for k in mapping) for row in p]
        if (projected == g) if order_matters else (Counter(projected) == Counter(g)):
            return True
    return False


def _mappings(g: list[tuple], p: list[tuple], n_gold: int, n_pred: int):
    """정답 열마다 값 묶음이 같은 생성 열 후보를 찾고, 서로 다른 열끼리의 대응을 내놓는다."""
    def column(rows, i):
        return Counter(row[i] for row in rows)

    pred_columns = [column(p, k) for k in range(n_pred)]
    candidates = [[k for k in range(n_pred) if pred_columns[k] == column(g, j)] for j in range(n_gold)]
    tried = 0
    for mapping in product(*candidates):
        if len(set(mapping)) < n_gold:
            continue
        tried += 1
        if tried > MAX_MAPPINGS:
            return
        yield mapping
