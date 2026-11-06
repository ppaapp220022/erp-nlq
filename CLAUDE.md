# erp-nlq

ERP(Odoo) 데이터를 한국어로 물으면 SQL로 바꿔 답한다. LLM이 어떤 SQL을 만들어도 사용자 권한 밖의 데이터는 나오지 않게 코드로 강제하고, 정확도와 권한 우회 건수를 같은 평가 세트로 잰다. 1인 프로젝트이고, 기간 대신 마일스톤 순서를 따른다.

- 구조와 신뢰 경계: [docs/architecture.md](docs/architecture.md)
- 일정, 완료 기준, 현재 위치: [docs/plan.md](docs/plan.md). 작업을 시작하기 전에 읽고, 끝나면 체크박스를 갱신한다.
- 결정 기록: [docs/adr/](docs/adr/) · 실제로 부딪힌 문제: 구글 드라이브 `ERP 자연어 질의 시스템/troubleshooting` 폴더(폴더 id `1ZJQdQkBsnkV3JXchqeyoQBEc_ugseilt`, 비공개). 레포에는 올리지 않는다(`docs/troubleshooting/`은 gitignore).

## 명령

```bash
docker compose up -d                 # Odoo 19 + Postgres 16(pgvector), 둘 다 127.0.0.1에만 공개
./scripts/db-readonly-role.sh        # 질의용 역할 nlq_readonly 생성·권한 재적용 (멱등)
./scripts/db-seed.sh                 # 영업 사원 추가와 담당자 배정, Odoo와 SQL 수 비교 출력 (멱등)
./scripts/db-snapshot.sh save|restore <파일>   # snapshots/ 에 DB + filestore 저장·복원
./scripts/db-schema.sh               # nlq_readonly가 읽는 열 목록을 db/schema.txt로 (generate 프롬프트용)
uv run --directory backend pytest  # 백엔드 테스트 (Python 3.12, uv 필요)
uv run --directory backend nlq "질문" --user sales.kim   # 터미널에서 질문 → SQL → 결과. --sql, --users 참고
uv run --directory backend nlq-eval [--model ...] [id ...]   # 평가 문항 채점, 영역별 정확도 (eval/README.md)
./scripts/odoo-shell.sh <파일.py>     # Odoo ORM(env)으로 Python 실행. 권한 조사는 scripts/odoo_access_report.py
```

DB를 처음 만드는 방법은 [README.md](README.md). Docker CLI가 PATH에 없으면 `/Applications/Docker.app/Contents/Resources/bin`을 더한다.
Odoo 소스는 컨테이너 안 `/usr/lib/python3/dist-packages/odoo`에 있다. 실행 중인 버전과 같으므로 근거로 인용할 때는 이것을 읽는다.

## 절대 규칙

1. **권한은 `execute()`가 강제한다.** LLM이 만든 SQL과 `generate()`의 출력은 신뢰하지 않는다. DB에 닿는 경로는 `execute()` 하나뿐이다.
2. **질의 계층은 `nlq_readonly`로만 접속한다.** `odoo` 계정은 superuser라 RLS를 건너뛴다. 평가·테스트에서도 쓰지 않는다.
3. **Odoo 코드는 수정하지 않는다.** Odoo(LGPL)와 WrenAI(일부 AGPL) 코드를 이 레포에 복사하지 않는다. DB에는 `db/`의 역할·정책 SQL만 적용한다.
4. **평가용 질문(`eval/questions/`)은 프롬프트 예시나 학습 데이터로 쓰지 않는다.** 예시는 `eval/examples/`에서만 가져온다.
5. **권한 계층을 바꾸면 우회 테스트를 하나 이상 추가한다.** 찾은 우회 경로는 고치기 전에 실패하는 테스트로 먼저 남긴다.
6. **로그와 감사 기록에 개인정보를 남기지 않는다.**
7. **범위를 늘리지 않는다.** plan.md의 1·2단계 밖 기능은 "2차 목록"에만 적는다.

## 작업 방식

- 작업 단위 하나 = 브랜치 하나 = PR 하나. main에 직접 커밋하지 않는다.
- 브랜치는 기간(주차·마일스톤)이 아니라 **작업 단위**로 나눈다. 이름은 영어로 쓰고 `feat/`, `fix/`, `chore/`, `docs/`로 시작한다(예: `feat/sql-guard`, `chore/db-snapshot`).
- **브랜치 이름만 영어**로 쓴다. 커밋과 PR은 제목과 본문 모두 한국어로 쓰고, 제목은 `type: 한국어 요약` 형식이다(type은 영어).

  ```
  feat: sqlglot으로 영업 사원 범위 강제

  - sale_order를 권한 조건이 걸린 서브쿼리로 바꿔 끼운다
  - 담당자 없는 주문도 포함 (Odoo sale_order_personal_rule과 동일)
  ```
- "끝났다"는 plan.md의 완료 기준으로 판단한다. 실행해서 확인하지 못했으면 못 했다고 적는다.
- 생성과 평가는 Claude API로 한다(`ANTHROPIC_API_KEY`, `EVAL_MODEL`). 개발에는 Haiku, 결과 표용 측정에는 Opus를 쓴다.
- 점수나 숫자가 바뀌는 작업은 전후 숫자와 잰 모델을 함께 기록한다. Haiku 점수와 Opus 점수를 섞지 않는다.
- 미리 보고 막은 위험은 ADR에, 실제로 부딪힌 문제는 드라이브 troubleshooting 폴더에 `YYYY-MM-DD-주제.md`로 적는다(상황·원인·시도·해결·배운 점).
- 브랜치·PR·머지 절차(스쿼시 머지, main 따라잡기는 리베이스, 쌓인 PR, 워크플로 변경 PR 처리)는 [docs/pr-workflow.md](docs/pr-workflow.md)를 따른다. 머지와 브랜치 보호 변경은 사용자 승인 후에만 한다.
- PR은 필수 체크 두 개를 통과해야 머지된다. `checks`는 결정적 검사이고, `ai-review`는 Claude가 [.github/review/prompt.md](.github/review/prompt.md) 기준으로 검토해 blocking이 있으면 실패한다. 리뷰 지침은 기준 브랜치의 것을 쓴다. 지침을 바꾸는 PR은 이유를 본문에 적는다.
