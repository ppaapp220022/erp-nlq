"""sqlglot 구문 트리로 SQL을 검증하고 행 범위를 끼워 넣는다 (docs/architecture.md "guard").

허용 목록 방식이다. 트리의 모든 노드가 아래 목록에 있어야 하고, 모르는 노드·함수·테이블은 거부한다.
검증한 트리를 다시 SQL로 만들어 실행하므로, 원문이 아니라 guard가 본 것이 DB로 간다.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from nlq.identity import TABLES, can_read, row_scope
from nlq.models import GuardError, User

DIALECT = "postgres"

QUERIES = (exp.Select, exp.Union, exp.Intersect, exp.Except)

# 구조와 연산자
STRUCTURE = (
    *QUERIES, exp.With, exp.CTE, exp.Subquery, exp.From, exp.Join, exp.Lateral, exp.Where, exp.Group,
    exp.Having, exp.Order, exp.Ordered, exp.Limit, exp.Offset, exp.Distinct, exp.Alias, exp.TableAlias,
    exp.Table, exp.Column, exp.Identifier, exp.Star, exp.Literal, exp.Boolean, exp.Null, exp.Paren,
    exp.Tuple, exp.Array, exp.And, exp.Or, exp.Not, exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.NullSafeEQ, exp.NullSafeNEQ, exp.Is, exp.In, exp.Any, exp.All, exp.Exists, exp.Between, exp.Like,
    exp.ILike, exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.Neg, exp.DPipe, exp.Case, exp.If,
    exp.Window, exp.WindowSpec, exp.Filter, exp.Interval, exp.Cast, exp.DataType, exp.DataTypeParam,
    exp.JSONPath, exp.JSONPathKey, exp.JSONPathRoot,
    # jsonb 키 존재(?, ?|, ?&)와 포함(@>, <@). 이미 읽을 수 있는 열끼리 비교만 하고 다른 행·테이블을 열지 않는다.
    # Odoo 19의 회사별 값(standard_price 등)이 {"회사 id": 값} jsonb라 `standard_price ? '1'` 꼴로 쓰인다.
    exp.JSONBContainsTopKey, exp.JSONBContainsAnyTopKeys, exp.JSONBContainsAllTopKeys,
    exp.ArrayContainsAll, exp.ArrayContainedBy,
)

# 함수. sqlglot이 이름을 아는 함수는 전용 노드로 파싱되고, 모르는 함수는 Anonymous가 된다.
FUNCTIONS = (
    exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max, exp.GroupConcat,
    exp.Coalesce, exp.Nullif, exp.Greatest, exp.Least, exp.Round, exp.Abs, exp.Floor, exp.Ceil,
    exp.Lower, exp.Upper, exp.Length, exp.Concat, exp.Substring, exp.Trim,
    exp.Extract, exp.TimestampTrunc, exp.DateTrunc, exp.TimeToStr, exp.CurrentDate, exp.CurrentTimestamp,
    exp.JSONExtract, exp.JSONExtractScalar,
    exp.RowNumber, exp.Rank, exp.DenseRank,
)
ANONYMOUS = {"age"}  # 전용 노드가 없는 함수 중 허용하는 것

# 날짜 부분 이름 (EXTRACT(year FROM ...), INTERVAL '1' day 등). 그 밖의 맨 단어(Var)는 거부한다.
DATE_PARTS = {
    "year", "quarter", "month", "week", "day", "hour", "minute", "second", "dow", "doy", "epoch",
    "years", "months", "weeks", "days", "hours", "minutes", "seconds",
}

T = exp.DataType.Type
TYPES = {
    T.INT, T.BIGINT, T.SMALLINT, T.DECIMAL, T.DOUBLE, T.FLOAT, T.TEXT, T.VARCHAR, T.CHAR,
    T.DATE, T.TIMESTAMP, T.TIMESTAMPTZ, T.BOOLEAN, T.INTERVAL,
}

# joins: 괄호로 묶은 조인 `(a JOIN b ON ...)`은 첫 테이블에 나머지 조인이 붙은 꼴로 파싱된다
TABLE_ARGS = {"this", "db", "alias", "only", "joins"}
ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def guard(sql: str, user: User, max_rows: int = 1_000, scope_rows: bool = True) -> str:
    """검증하고 재작성한 SQL을 돌려준다. 하나라도 걸리면 GuardError.

    1. 문장 하나, SELECT(CTE·UNION 포함)
    2. 노드·함수·형 허용 목록
    3. 테이블: CTE가 아니면 사용자가 읽을 수 있는 허용 테이블
    4. 테이블마다 행 범위가 걸린 서브쿼리로 바꾼다. scope_rows=False면 건너뛴다(RLS 정책이 거는 경로, ADR 0005)
    5. 바깥 LIMIT은 max_rows + 1 이하 (execute가 넘친 것을 알아챈다)
    """
    try:
        tree = _parse(sql)
        for node in tree.walk():
            _check_node(node)
        tables = [t for t in tree.find_all(exp.Table) if not _is_cte_reference(t)]
        for table in tables:
            _check_table(table, user)
        if scope_rows:
            for table in tables:
                table.replace(_scoped(table, user))
        _force_limit(tree, max_rows + 1)
        return tree.sql(dialect=DIALECT, comments=False)
    except RecursionError as e:
        raise GuardError("SQL이 너무 깊게 중첩됐다") from e


def _parse(sql: str) -> exp.Expression:
    try:
        statements = sqlglot.parse(sql, read=DIALECT)
    except SqlglotError as e:
        raise GuardError(f"SQL을 해석하지 못했다: {str(e).splitlines()[0]}") from e
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise GuardError("SQL 문장은 하나만 받는다")
    tree = statements[0]
    if not isinstance(tree, QUERIES):
        raise GuardError("SELECT 문만 실행한다")
    return tree


def _check_node(node: exp.Expression) -> None:
    if isinstance(node, exp.Anonymous):
        if node.name.lower() not in ANONYMOUS:
            raise GuardError(f"허용하지 않는 함수: {node.name}")
        return
    if isinstance(node, exp.Var):
        if isinstance(node.parent, exp.Limit) and node.name.upper() == "ALL":
            return  # LIMIT ALL. _force_limit이 바꾼다
        if node.name.lower() not in DATE_PARTS:
            raise GuardError(f"허용하지 않는 키워드: {node.name}")
        return
    if not isinstance(node, STRUCTURE + FUNCTIONS):
        raise GuardError(f"허용하지 않는 구문: {node.key}")
    if isinstance(node, exp.DataType) and node.this not in TYPES:
        raise GuardError(f"허용하지 않는 형: {node.sql(dialect=DIALECT)}")
    if isinstance(node, exp.Select) and (node.args.get("into") or node.args.get("locks")):
        raise GuardError("SELECT INTO와 FOR UPDATE는 받지 않는다")


def _name(identifier: exp.Identifier) -> str:
    # Postgres는 따옴표 없는 이름의 ASCII 대문자만 소문자로 바꾼다. 따옴표가 있으면 그대로다.
    # str.lower()는 켈빈 기호(U+212A) 같은 문자도 ASCII로 바꿔 Postgres와 달라진다.
    return identifier.name if identifier.quoted else identifier.name.translate(ASCII_LOWER)


def _is_cte_reference(table: exp.Table) -> bool:
    """이 테이블 참조가 Postgres에서 CTE를 가리키는지. 확실하지 않으면 실제 테이블로 본다(더 엄격한 쪽)."""
    if table.args.get("db") or table.args.get("catalog") or not isinstance(table.this, exp.Identifier):
        return False
    name = _name(table.this)
    child, node = table, table.parent
    while node is not None:
        with_ = node if isinstance(node, exp.With) else None
        if with_ is not None:
            names = [_name(cte.args["alias"].this) for cte in with_.expressions]
            # 재귀 아닌 WITH 안에서는 앞서 정의된 CTE만 보인다. 자기 자신과 뒤의 것은 실제 테이블이다.
            k = next(i for i, cte in enumerate(with_.expressions) if cte is child)
            visible = names[: k + 1] if with_.args.get("recursive") else names[:k]
            if name in visible:
                return True
        elif isinstance(node.args.get("with_"), exp.With) and node.args["with_"] is not child:
            # WITH가 붙은 쿼리의 본문: 그 WITH의 CTE가 모두 보인다.
            # sqlglot이 인자 이름을 바꾸면 여기를 못 지나 CTE도 실제 테이블로 보고 거부한다(실패 시 닫힘).
            if name in {_name(cte.args["alias"].this) for cte in node.args["with_"].expressions}:
                return True
        child, node = node, node.parent
    return False


def _check_table(table: exp.Table, user: User) -> None:
    if set(k for k, v in table.args.items() if v) - TABLE_ARGS or not isinstance(table.this, exp.Identifier):
        raise GuardError(f"허용하지 않는 FROM 항목: {table.sql(dialect=DIALECT)}")
    db = table.args.get("db")
    if db is not None and _name(db) != "public":
        raise GuardError(f"허용하지 않는 스키마: {db.name}")
    name = _name(table.this)
    if name not in TABLES:
        raise GuardError(f"허용하지 않는 테이블: {name}")
    if not can_read(name, user):
        raise GuardError(f"이 사용자는 {name} 테이블을 읽을 수 없다")


def _scoped(table: exp.Table, user: User) -> exp.Subquery:
    """`t AS a` → `(SELECT * FROM t WHERE <행 범위>) AS a`. 별칭이 없으면 테이블 이름을 별칭으로 쓴다.

    괄호 조인의 첫 테이블이면 붙어 있던 조인을 바꾼 서브쿼리로 옮긴다. 조인 안 테이블은 각자 따로 바뀐다.
    """
    name = _name(table.this)
    rule = TABLES[name]
    columns = ", ".join(rule.columns) if rule.columns else "*"
    inner = sqlglot.parse_one(f"SELECT {columns} FROM {name} WHERE {row_scope(name, user)}", read=DIALECT)
    alias = table.args.get("alias") or exp.TableAlias(this=exp.to_identifier(name))
    return exp.Subquery(this=inner, alias=alias.copy(), joins=table.args.get("joins"))


def _force_limit(tree: exp.Expression, limit: int) -> None:
    current = tree.args.get("limit")
    value = current.expression if isinstance(current, exp.Limit) else None
    if isinstance(value, exp.Literal) and value.is_int and int(value.this) <= limit:
        return
    tree.set("limit", exp.Limit(expression=exp.Literal.number(limit)))
