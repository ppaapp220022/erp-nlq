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

파일 하나에 문항 하나를 YAML로 쓴다. 파일 이름은 `<영역>-<번호>.yaml`이다(예: `sales-001.yaml`).

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
