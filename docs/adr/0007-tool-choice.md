# 0007. 도구 선택: Odoo, sqlglot, 비교 대상 WrenAI

- 상태: 채택
- 날짜: 2026-11-08

## 맥락

이 프로젝트가 기대는 외부 도구는 셋이다. 데이터와 권한 모델을 주는 ERP(Odoo), LLM이 만든 SQL을 구문 트리로 읽고 고쳐 쓰는 파서(sqlglot), 결과를 견줄 기존 자연어 질의 도구(WrenAI). 셋 모두 버전이 바뀌면 점수나 권한 결과가 달라질 수 있다. 그래서 무엇을 왜 골랐는지와 함께 버전을 어떻게 고정했는지, 도구가 아직 살아 있는지를 한곳에 적는다.

ERP를 Odoo Community 19로 고른 이유와 ERPNext를 뺀 이유는 [0001](0001-odoo-as-data-source.md)에 있다. 여기서는 반복하지 않고 버전 고정과 활성도만 적는다.

## 결정

### Odoo Community 19.0 (데이터 소스)

- 선택 이유: [0001](0001-odoo-as-data-source.md).
- 고정: `docker-compose.yml`에서 이미지 태그와 digest를 함께 쓴다. 태그가 매일 새 빌드로 바뀌기 때문이다.
  - `odoo:19.0@sha256:5e755c725b3c43cf0be16d579904e1418300db3a2c44952f928eaddbcb0cc16d` (주석: "19.0-20261102 빌드")
  - `pgvector/pgvector:pg16@sha256:0dd3149a06e4579a0d70d8fef9945636cd514005e7237deb27f9b67886f8dc4f`
  - 올릴 때는 스냅숏(`snapshots/erp-20261103.zip`)과 평가를 다시 만든다(같은 파일 주석).

### sqlglot (guard의 파서·재작성기)

- 선택 이유: guard는 SQL을 트리로 파싱하고, 테이블을 행 범위 서브쿼리로 바꿔 끼운 뒤 SQL을 **다시 만들어** 실행한다([architecture.md](../architecture.md)). 그래서 필요한 것은 (1) Postgres 방언 파싱, (2) 트리를 고치는 API, (3) 고친 트리를 다시 SQL로 내는 생성기, (4) 순수 Python이라 설치가 단순할 것이다. sqlglot은 넷을 다 갖췄다.
- 고정: `backend/pyproject.toml`에 `"sqlglot==30.29.0",  # guard가 sqlglot이 다시 만든 SQL을 실행하므로 버전을 고정한다`. `backend/uv.lock`도 `sqlglot 30.29.0`(sdist 업로드 2026-11-03)이다. 범위 지정(`>=`)을 쓰지 않는 이유는 생성기 출력이 바뀌면 실제로 실행되는 SQL이 바뀌기 때문이다. 올릴 때는 우회 테스트와 평가를 다시 돌린다.

### WrenAI (비교 기준 2의 상대)

- 쓰는 이유: 고르는 대상이 아니라 **견주는 대상**이다. 의미 계층(MDL)을 두고 자연어를 SQL로 바꾸는 오픈 소스 도구 중 널리 쓰이는 편이라(GitHub 별 약 1.8만, 2026-11-08), "이미 있는 도구보다 나은가"를 같은 50문항으로 보여 주기에 맞다. 이 프로젝트 코드에는 WrenAI를 넣지 않는다. 별도 컨테이너로 띄우고 평가 문항만 보내 답을 받는다.
- 고정: **아직 이 레포에서 고정하지 않았다.** 비교 기준 2 작업이 띄울 버전(이미지 digest 또는 릴리스 태그)을 정하면 그 PR이 이 절을 갱신한다.

## 고려한 대안

- **ERP:** ERPNext는 [0001](0001-odoo-as-data-source.md). Dolibarr도 후보였다. Dolibarr는 모듈별 권한을 PHP 코드 안에서 확인하는 구조라, Odoo처럼 행 단위 규칙("담당자가 본인이거나 없는 주문")이 DB에 도메인 식(`ir_rule`)으로 남아 있지 않다. 코드로 강제할 규칙의 근거(ADR [0003](0003-guard-rules-from-odoo-groups.md))를 ERP 데이터에서 뽑아 올 수 없어 뺐다. Dolibarr 소스까지 읽어 확인하지는 않았다.
- **파서:**
  - sqlparse: 토큰을 나누는 수준이고 문법을 검증하지 않는다. FROM 절 안의 테이블을 빠짐없이 찾는다는 보장이 없어 권한 강제에 쓸 수 없다.
  - pglast(Python의 libpg_query 바인딩)와 pg_query(Ruby·Go 등의 libpg_query 바인딩): Postgres 실제 파서를 쓰므로 파싱은 가장 정확하다. 하지만 트리가 Postgres 내부 노드 그대로라 서브쿼리 바꿔 끼우기 같은 재작성 코드가 길어지고, C 확장이라 빌드 환경을 탄다. pg_query는 Python 프로젝트에서 쓰려면 pglast를 거치게 된다. 파싱 정확도의 빈틈은 guard가 "모르는 구문은 거부"로 메우고, 재작성 결과는 우회 테스트와 Odoo 행 수 일치로 확인한다.
- **비교 대상:**
  - Vanna: 예시·문서를 검색해 프롬프트에 넣는 방식이라, 이 프로젝트가 이미 따로 재는 "검색(RAG)" 축(plan.md 2단계)과 겹친다. 의미 계층을 둔 WrenAI가 접근이 더 달라 비교할 거리가 많다.
  - LangChain SQL 에이전트: 라이브러리 조각이라 "도구 하나와 비교"가 되지 않고, 어떤 프롬프트·체인을 쓰느냐가 결과를 정한다.

## 결과

### 활성도 (2026-11-08 확인)

GitHub API(`gh api`)와 PyPI JSON으로 확인했다. 커밋 수는 해당 브랜치의 2026-10-09 이후 커밋이다.

| 도구 | 라이선스 | 최근 릴리스 | 최근 30일 커밋 | 마지막 커밋 |
|---|---|---|---|---|
| Odoo (`odoo/odoo`, 브랜치 19.0) | LGPL-3.0 (19.0 브랜치 `LICENSE`) | GitHub 릴리스를 쓰지 않는다. 이미지 `odoo:19.0`은 매일 새 빌드 | 736 | 2026-11-07 |
| sqlglot (`tobymao/sqlglot`) | MIT | PyPI 30.30.0 (2026-11-06). 09-03~11-06에 12번 릴리스 | 318 | 2026-11-07 |
| WrenAI (`Canner/WrenAI`) | 경로별 다중 라이선스(아래) | `wren-v0.17.1` (2026-10-30). 앱 릴리스 줄 `0.29.2`(2026-08-05) | 36 | 2026-11-02 |

- Odoo 저장소의 기본 브랜치는 이미 `20.0`이다(마지막 커밋 2026-11-08). 19.0은 다음 버전이 나온 뒤에도 수정 커밋이 계속 들어오는 안정 브랜치이고, 이 프로젝트는 digest로 묶었으므로 그 커밋들을 따라가지 않는다.
- sqlglot은 거의 매주 마이너 버전이 나온다. 고정 버전(30.29.0)은 2026-11-08 기준 한 버전 뒤다.
- 확인하지 못한 것: 세 저장소의 GitHub 주간 커밋 통계(`stats/commit_activity`)는 응답이 비어 있어 52주 추이를 보지 못했다. 위 커밋 수는 커밋 목록을 세어 얻었다.

### 라이선스와 "코드를 레포에 복사하지 않는다"

CLAUDE.md 절대 규칙 3은 Odoo(LGPL)와 WrenAI(일부 AGPL) 코드를 이 레포에 복사하지 않는다고 정한다. 이 레포는 퍼블릭이고, 두 라이선스는 소스를 섞어 배포할 때 의무가 생긴다.

- **Odoo(LGPL-3.0):** 이 프로젝트는 Odoo를 공식 이미지로 실행하고, DB에 `db/`의 역할·정책 SQL만 적용한다. Odoo 소스를 수정하거나 레포에 옮기지 않으므로 LGPL의 수정본 공개 의무가 이 레포에 걸리지 않는다. Record Rules를 근거로 인용할 때도 컨테이너 안 소스의 경로와 규칙 이름만 적고, 규칙은 우리 코드로 다시 쓴다(ADR [0003](0003-guard-rules-from-odoo-groups.md), [0005](0005-rls-vs-guard.md)).
- **WrenAI:** `LICENSE` 이력을 보면 처음(2024-03, 커밋 `156cfa7b4`)에는 Apache-2.0이었고, 2024-05-21 커밋 `638de2c5a`부터 2026-05까지 저장소 전체가 AGPL-3.0이었다. 2026-05-04 커밋 `e5b25eec5`로 경로별 다중 라이선스가 됐다. 2026-11-08 기준 `core/`·`sdk/`·`skills/`·`examples/`와 루트 파일은 Apache-2.0, `docs/`는 CC BY 4.0이고, AGPL-3.0은 "앞으로 생길 모듈"용으로 원문만 두었다. 그래서 규칙 3의 "일부 AGPL"은 지금 저장소 기준으로는 정확하지 않지만, (1) 비교에 예전 앱 릴리스 줄(0.29.x 이하, AGPL)을 쓸 수 있고, (2) AGPL 모듈이 다시 생길 수 있으며, (3) Apache-2.0 코드도 옮기면 고지 의무가 생기므로 규칙은 그대로 둔다. WrenAI는 별도 컨테이너로만 띄우고, 이 레포에는 띄우는 설정과 평가 결과만 둔다.
- **sqlglot(MIT):** 의존성으로 설치해 쓰기만 하므로 고지 외 의무가 없다.

### 감수하는 것

- 버전을 고정했으므로 상위 버전의 버그 수정(Odoo 19.0 브랜치, sqlglot 30.30.0 이후)을 자동으로 받지 않는다. 올릴 때마다 스냅숏·우회 테스트·평가를 다시 돌려야 한다.
- sqlglot은 Postgres 실제 파서가 아니다. Postgres는 받아들이지만 sqlglot이 잘못 읽는 구문이 있을 수 있다. guard는 모르는 구문을 거부하고, RLS 경로([0005](0005-rls-vs-guard.md))가 같은 규칙을 DB에서 한 번 더 건다.
- WrenAI 비교 결과는 그때 띄운 버전에 묶인다. 비교 기준 2(2026-11-08)는 **앱 릴리스 줄 0.29.2**를 이미지 digest로 고정해 썼다(wren-ui 0.32.3, wren-ai-service 0.29.3, wren-engine·ibis 0.22.0, digest는 [reference/wrenai.md](../reference/wrenai.md)). `wren-v0.x` 줄은 질문 → SQL 서비스가 없는 에이전트용 CLI라 비교 대상이 되지 않는다. 0.29.2는 AGPL 시절 코드이므로 레포 밖에서 컨테이너로만 띄웠다.

### 근거

- `docker-compose.yml`, `backend/pyproject.toml`, `backend/uv.lock`
- https://github.com/odoo/odoo (브랜치 19.0의 `LICENSE`), https://hub.docker.com/_/odoo
- https://github.com/tobymao/sqlglot, https://pypi.org/project/sqlglot/
- https://github.com/Canner/WrenAI (`LICENSE`, 릴리스 목록)
