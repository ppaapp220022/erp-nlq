# 평가

| 폴더 | 용도 | 프롬프트에 써도 되나 |
|---|---|---|
| `questions/` | 평가용 50문항. 점수는 여기서만 낸다 | **안 된다** (CLAUDE.md 절대 규칙 4) |
| `examples/` | few-shot 예시, RAG 예시 검색 대상 | 된다 |

같은 질문, 또는 숫자·이름만 바꾼 질문을 두 폴더에 함께 두지 않는다. 외부 데이터셋(Hugging Face odoo-sql-query-dataset 등)은 `examples/`에만 넣는다.

## 고정값

[config.yaml](config.yaml)의 `today`와 `snapshot`을 함께 쓴다. 데모 데이터의 날짜는 DB를 만든 날을 기준으로 생기므로, 스냅숏을 바꾸면 `today`도 바꾸고 정답을 다시 확인한다.

- "이번 달", "지난 분기", "30일 넘게 지난" 같은 표현은 `today` 기준으로 푼다.
- 정답 SQL과 생성 SQL 모두 `CURRENT_DATE`·`now()` 대신 `today` 값을 쓴다.

## 문항 형식

파일 하나에 문항 하나를 YAML로 쓴다. 파일 이름은 `<영역>-<번호>.yaml`이다(예: `sales-001.yaml`). 영역 이름은 `sales`(판매), `purchase`(구매), `stock`(재고), `account`(회계)다.

```yaml
id: sales-001
area: 판매            # 판매 | 구매 | 재고 | 회계
role: sales.kim       # 질문하는 사용자 login(eval/users.toml). 정답은 이 사용자의 권한 범위 안의 결과다
question: 이번 달 거래처별 매출 상위 5곳
gold_sql: |
  SELECT ...
order_matters: true   # 결과 행 순서까지 비교할지 (상위 N 같은 질문)
notes: 매출 = 확정 고객 송장 - 환불, 부가세 제외
```

채점은 `gold_sql`과 생성 SQL을 같은 사용자 권한으로 실행한 결과 집합을 비교한다. 열 이름과 반올림 차이는 무시하고, `order_matters`가 false면 행 순서도 무시한다.

- `gold_sql`에는 권한 조건(담당자·회사)을 쓰지 않는다. 채점할 때 `execute()`가 `role` 사용자의 범위를 두 SQL에 똑같이 건다. 범위는 Odoo가 그 사용자에게 보여 주는 것과 같다(`backend/tests/test_odoo_scope.py`).
- `role`은 그 질문을 실제로 할 만한 역할로 고른다. 역할 밖 데이터를 묻는 질문은 권한 우회 테스트로 따로 둔다.
- 정답 결과가 비면 안 된다. 형식과 정답 SQL 실행은 `backend/tests/test_eval_questions.py`가 검사한다.
- 정답 숫자는 문항 파일에 적지 않는다. 확인한 값은 PR에만 남긴다.
- "품목별"은 변형(`product_product`) 단위로 묶는다. 재고·주문·발주 라인이 변형을 가리키기 때문이다. 이름은 템플릿 이름을 보여 주므로, 변형이 여럿인 품목은 같은 이름이 여러 행 나온다.

## 예시 형식

`examples/`도 파일 하나에 예시 하나다. 파일 이름은 문항과 같은 규칙이고, `id`는 `ex-`를 앞에 붙인다. 정답 열 이름은 `sql`이다.

```yaml
id: ex-sales-001
area: 판매
role: admin           # 예시 SQL을 확인한 사용자. 검색할 때는 질문한 사용자가 읽을 수 있는 테이블만 쓰는 예시를 고른다
question: 유효기간이 앞으로 30일 안에 끝나는 견적. 주문 번호, 고객, 유효기간
sql: |
  SELECT ...
notes: 견적 = draft·sent
```

- 문항과 같은 질문, 숫자·이름만 바꾼 질문, 같은 결과를 내는 질문은 두지 않는다. `test_eval_questions.py`가 질문 문장 일치, 글자 2-gram 유사도(0.5 이상), 결과 일치를 검사한다. 유사도 기준은 느슨하므로 예시를 더할 때는 가장 가까운 문항을 눈으로도 확인한다.
- 예시 SQL도 `role` 사용자로 실행해 결과가 비지 않아야 한다.

## 채점

```bash
uv run --directory backend nlq-eval                            # 전체, EVAL_MODEL(기본 claude-haiku-5-5)
uv run --directory backend nlq-eval --model claude-opus-5-5    # 결과 표용 측정
uv run --directory backend nlq-eval sales-001 stock-002        # 일부만
uv run --directory backend nlq-eval --prompt schema            # 비교 기준 1: OKF 묶음 없이 (기본 okf)
uv run --directory backend nlq-eval --retries 0                # 자기 수정 없이 (기본 1회)
uv run --directory backend nlq-eval --retrieve embedding       # 비슷한 예시 3개를 사용자 메시지에 넣어 (기본 keyword, none은 넣지 않음)
```

비교 규칙은 [backend/nlq/scoring.py](../backend/nlq/scoring.py)에 있다.

- 열 이름은 무시한다. 생성 결과에 열이 더 있어도(이름·id 열을 덧붙인 경우) 정답 열이 모두 같은 행에 들어 있으면 맞다. 행은 더 있거나 모자라면 틀리다.
- 숫자는 소수 둘째 자리로 맞춘다(5와 5.00은 같다). 자정 시각의 timestamp는 날짜와 같다. 시각이 있는 timestamp는 날짜와 다르다. 질문이 날짜(주문일 등)를 물으면 날짜로 내야 맞다.
- 행 수 제한(1,000행)으로 잘린 결과는 틀린 것으로 본다.
- 결과는 `correct`, `wrong`, `generation_error`, `guard_rejected`, `execution_error` 중 하나다. 정답 SQL이 실행되지 않으면 채점을 멈춘다.
- 실행 결과는 `eval/results/<시각>-<모델>-<변형>.json`(git 제외)에 모델, 프롬프트 변형(`okf`·`schema`)과 버전(시스템 프롬프트 해시)과 함께 남는다. 점수는 모델별로 따로 적고, Haiku와 Opus 점수를 섞지 않는다.
- 생성 SQL이 실행되지 않으면(guard 거부·실행 오류) 오류를 넣어 한 번 다시 만들고 마지막 시도를 채점한다(자기 수정, `--retries`, 기본 1). 결과 표의 "재시도"는 다시 만든 문항 수, "재시도로 정답"은 그중 맞힌 수다. 결과 파일에는 `retries` 설정과 문항별 `retried`·`first_error`가 남는다. M4 결과 표는 자기 수정 전이라 `--retries 0`과 같다.
- 예시 검색은 `NLQ_RETRIEVE`(또는 `--retrieve`)로 고른다. `keyword`는 질문 글자 2-gram BM25, `embedding`은 다국어 문장 임베딩이고, 질문한 사용자가 읽을 수 있는 테이블만 쓰는 예시 중 3개를 고른다([backend/nlq/retrieve.py](../backend/nlq/retrieve.py), [ADR 0004](../docs/adr/0004-example-retrieval-in-memory.md)). 결과 파일 이름에 검색 방식이 붙고, 문항별 `examples`에 넣은 예시 id, `examples_version`에 예시 묶음 해시가 남는다.
- 프롬프트 변형은 `NLQ_PROMPT`(또는 `--prompt`)로 고른다. `okf`는 지침 + 열 목록 + OKF 묶음, `schema`는 OKF 묶음과 그것을 가리키는 지침 한 줄만 뺀 비교 기준 1이다([backend/nlq/prompt.py](../backend/nlq/prompt.py)).
