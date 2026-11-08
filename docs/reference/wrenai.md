# WrenAI 비교 환경 (M6 비교 기준 2)

같은 50문항(`eval/questions/`)을 WrenAI에 묻고, 같은 채점 규칙(`nlq/scoring.py`)으로 잰다. 결과는 [plan.md "M6 WrenAI 비교"](../plan.md#m6-wrenai-비교).
WrenAI 코드와 compose 파일은 레포에 넣지 않는다(일부 AGPL, CLAUDE.md 절대 규칙 3). 레포 밖 `~/dev/wrenai-compare/0.29.2/`에서 띄우고, 아래에 설정만 적는다.

## 버전

WrenAI는 2026-10의 `wren-v0.x`부터 에이전트용 CLI·문맥 계층으로 바뀌었고, 질문 → SQL을 하는 서비스(wren-ai-service)와 UI·API는 상용판으로 옮겼다. 그래서 질문 → SQL을 스스로 하는 마지막 오픈소스 릴리스 **0.29.2**(2026-08-05)를 쓴다.

| 이미지 | 태그 | digest (멀티 아키텍처 인덱스) |
|---|---|---|
| ghcr.io/canner/wren-ui | 0.32.3 | `sha256:497d963746d682cb38c28dc109fe365d5898ed7e4456803ce16cc9a02e6a0ee3` |
| ghcr.io/canner/wren-ai-service | 0.29.3 | `sha256:6afc02ce5ab696deef5a287ca3d2b71e0a9467b180dd1b276679095703b7a80f` |
| ghcr.io/canner/wren-engine | 0.22.0 | `sha256:08dd4069452935cb76986dbd090e7776fa0da53bdcc5f94120f2fd005d9ceb91` |
| ghcr.io/canner/wren-engine-ibis | 0.22.0 | `sha256:54f1f060d64982c09d9b5f68420a95810a40e37da83449af8f68e8f25ae86940` |
| ghcr.io/canner/wren-bootstrap | 0.1.5 | `sha256:731c3085cee5c87a79b07d27c9d10eb35f4830b0cac46a51ac8e9f6606698ada` |
| qdrant/qdrant | v1.15.0 | `sha256:709bd2656bb929b745a956260f61a6395d09f8eed72c5bf2131985ae70f95974` |
| ollama/ollama (임베딩) | 0.40.5 | `sha256:5d3a2f25f9825628daba94dc0b1d421c7d57d6c03ae5faa9ba050e058bab8241` |

## 띄우는 법

0.29.2의 `docker/docker-compose.yaml`, `.env.example`, `config.example.yaml`을 받아 다음만 바꾼다.

- **이미지**: 위 표의 `태그@digest`로 고정한다. `PLATFORM=linux/arm64`.
- **포트**: wren-ui `127.0.0.1:3100:3000`(3000은 이 레포 화면이 쓴다), wren-ai-service `127.0.0.1:5555:5555`, ibis-server `127.0.0.1:8100:8000`(러너가 Wren SQL을 Postgres SQL로 바꿀 때 쓴다). 나머지는 공개하지 않는다.
- **DB**: ibis-server를 erp-nlq compose 네트워크(`erp-nlq_default`)에도 붙여 `db:5432`로 접속한다.
- **텔레메트리**: `TELEMETRY_ENABLED=false`, PostHog 키 비움, `langfuse_enable: false`.
- **LLM**: `anthropic/claude-haiku-5-5`(litellm), `max_tokens: 4096`. `.env`에 이 레포 `.env`의 `ANTHROPIC_API_KEY`. claude-haiku-5-5는 `temperature`를 받지 않아 넣지 않는다(이 레포 `generate()`도 넣지 않는다).
- **임베딩**: Anthropic은 임베딩 모델이 없어 ollama 컨테이너의 `bge-m3`(다국어, 1024차원)를 쓴다. `ollama/bge-m3`, `api_base: http://ollama:11434`, qdrant `embedding_model_dim: 1024`. 처음 한 번 `docker compose exec ollama ollama pull bge-m3`.
- 나머지 설정(파이프라인, `table_retrieval_size: 10`, `max_sql_correction_retries: 3`, `allow_intent_classification` 등)은 기본값 그대로다.

```bash
cd ~/dev/wrenai-compare/0.29.2 && docker compose up -d
```

## DB 역할 `nlq_wren`

WrenAI(ibis-server)는 쿼리마다 `CREATE TEMPORARY VIEW`로 결과 열의 형을 읽는다. `nlq_readonly`는 읽기 전용 트랜잭션이고 임시 객체 권한이 없어 연결 확인부터 실패한다(`cannot execute CREATE VIEW in a read-only transaction`). 그래서 `nlq_readonly`의 멤버 역할을 따로 만든다([db/wren_role.sql](../../db/wren_role.sql)).

- 테이블 권한은 `nlq_readonly`에서 상속받는다. 허용 테이블 13개 + `res_users` 5개 열만 읽고, `account_move_line` 등은 권한이 없다.
- RLS 정책 `nlq_guard`(`TO nlq_readonly USING (true)`)가 멤버에게도 적용되어 행은 `nlq_readonly`와 같다. 즉 행 범위가 없다.
- 읽기 전용 설정만 끄고 임시 객체(`TEMPORARY`)를 연다. 쓰기 권한이 있는 테이블은 없다(`UPDATE sale_order` → permission denied 확인).
- 질의 계층(`execute()`)은 이 역할을 쓰지 않는다.

```bash
set -a; source .env; set +a
docker compose exec -T db psql -U odoo -d "$ODOO_DB_NAME" -q \
  -v wren_user=nlq_wren -v wren_password="$NLQ_RO_PASSWORD" -v ro_user=nlq_readonly -v db_name="$ODOO_DB_NAME" \
  < db/wren_role.sql
```

## WrenAI에 넣는 것

`uv run --directory backend nlq-eval-wren setup`이 wren-ui API로 프로젝트를 새로 만든다. 평가 문항(`eval/questions/`)과 되묻기 세트(`eval/clarify/`)는 넣지 않는다.

| 항목 | 내용 | 출처 |
|---|---|---|
| 데이터 소스 | Postgres `db:5432/erp`, 사용자 `nlq_wren` | — |
| 모델 | `nlq_wren`이 보는 테이블 14개 전부, 열 전부. 모델 이름은 WrenAI가 붙이는 `public_<테이블>` | — |
| 모델 설명 | 테이블 문서 본문(앞머리 제외), 표시 이름은 테이블 이름 | `knowledge/tables/*.md` 14개 |
| 관계 | 테이블 문서의 "`열` → [테이블]" 표기 14개, 다대일. `nlq_wren`은 FK 제약을 볼 수 없어 WrenAI 자동 추천은 0개였다 | `knowledge/tables/*.md` |
| 전역 지침 | 오늘 날짜(2026-11-03, 이 레포 프롬프트와 같은 문장), 모델 이름 규칙, 함정 8·흐름 2·지표 2 문서 본문(1,000자 단위로 나눔) | `eval/config.yaml`, `knowledge/` |
| SQL 예시 | 예시 40개 중 31개. 테이블 이름을 모델 이름으로만 바꾼다. 9개는 WrenAI가 검증에서 거부했다: jsonb `->>` 미지원 8개(품목 이름 등 번역 열), interval과 정수 비교 1개 | `eval/examples/` |
| 언어 | 한국어(KO) | — |

이 레포 시스템(OKF + 키워드 검색)이 받는 것과 같은 재료다. 다른 점은 넣는 방식이다. 이 레포는 역할이 볼 수 있는 OKF 문서를 전부 프롬프트에 넣고 예시를 3개 고르며, WrenAI는 모델·지침·예시를 임베딩으로 검색해 고른다. WrenAI는 역할을 모르므로 거르지 않는다.

## 채점

`uv run --directory backend nlq-eval-wren run`. 문항마다 `generate_sql`(wren-ui `/api/v1/generate_sql`, WrenAI의 의도 분류·검색·추론·생성·자기 수정을 모두 탄다)로 Wren SQL을 받고 두 가지로 채점한다. 정답은 둘 다 그 문항 `role` 사용자의 범위로 `execute()`한 `gold_sql` 결과다.

| | 실행 | 행 범위 |
|---|---|---|
| execute() | Wren SQL을 ibis-server dry-plan으로 Postgres SQL로 바꾸고, `erp.` 카탈로그만 뗀 뒤(guard가 카탈로그 붙은 이름을 거부한다) 우리 `execute()`로 role 사용자에게 실행 | guard가 건다 |
| 직접 실행 | wren-ui `/api/v1/run_sql` | 없음 (`nlq_wren` = `nlq_readonly`가 읽는 전부) |

- **우회**: 같은 SQL의 직접 실행 결과가 execute() 결과와 다른 문항. 범위 밖 행(다른 영업 사원의 주문, 역할 밖 테이블)이 결과에 섞였다는 뜻이다. 둘 중 하나가 실행되지 않으면 세지 않는다.
- 직접 실행 결과와 비교할 때만 jsonb 값을 JSON 문자열로 맞춘다. `execute()`는 jsonb를 dict로, WrenAI는 문자열로 돌려줘서, 같은 행인데 우회로 잘못 세는 일이 있었다(구매 2건).
- WrenAI는 질문 하나에 LLM을 여러 번 불러 API 분당 토큰 한도에 걸리기 쉽다. 한도 오류(`rate_limit`)일 때만 60초 쉬고 최대 5번 다시 묻는다. 다른 오류는 생성 실패로 센다.
- 결과는 `eval/results/*-wrenai-*.json`(git 제외). 채점 규칙만 고쳤을 때는 `run --rescore <결과.json>`으로 저장한 SQL을 다시 채점한다(WrenAI에 다시 묻지 않는다).

## 셋업에서 막힌 것

- wren-ui는 배포할 때 AI 서비스의 색인을 약 28초만 기다리고(하드코딩), 넘으면 배포를 실패로 기록한다. CPU에서 도는 bge-m3로 열 600여 개를 색인하는 데 약 9분 걸렸다. 그래서 `setup`은 배포 실패로 멈춘다. 색인이 끝나면(`curl 127.0.0.1:5555/v1/semantics-preparations/<해시>/status`가 `finished`) wren-ui의 배포 기록을 성공으로 바꾸고 나머지를 넣는다.

  ```bash
  docker compose exec -T wren-ui node -e "require('better-sqlite3')('/app/data/db.sqlite3').prepare(\"update deploy_log set status='SUCCESS', error=null where hash=?\").run('<해시>')"
  uv run --directory backend nlq-eval-wren setup --resume   # 지침·예시만 넣는다
  ```
- WrenAI 엔진(DataFusion)은 jsonb `->>`를 지원하지 않는다. 예시 9개가 거부되고, 품목 이름처럼 번역 jsonb 열을 꺼내야 하는 문항은 WrenAI가 열을 문자열로 캐스트해 `{"en_US": ...}`를 낸다.
- 경위는 드라이브 troubleshooting `2026-11-08-wrenai-setup.md`.
