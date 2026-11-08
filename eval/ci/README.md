# CI 평가 (M6)

`checks`가 PR과 main 푸시마다 두 가지를 이 폴더로 돈다([.github/workflows/checks.yml](../../.github/workflows/checks.yml)).

1. **축소 DB 위의 backend 테스트.** [erp-ci.sql.gz](erp-ci.sql.gz)를 빈 Postgres에 복원하고 `nlq_readonly`·`nlq_rls` 역할과 RLS 정책을 건 뒤(`scripts/db-ci-restore.sh`) `pytest`를 돈다. 권한 우회 테스트, Odoo 행 수 일치, 보고서 합계 대조, 평가 정답 SQL 실행이 모두 여기서 돈다. DB 테스트가 하나라도 건너뛰어지면 실패한다.
2. **평가 20문항.** [questions.yaml](questions.yaml)의 문항을 claude-haiku-5-5로 돌린다(`nlq-eval --ci`). `min_correct`보다 적게 맞히면 실패한다. 결과 표는 작업 요약에 남는다. API 키는 레포 시크릿 `ANTHROPIC_API_KEY`이고, 시크릿이 없는 포크 PR에서는 실패한다.

## 축소 덤프

`./scripts/db-ci-fixture.sh`가 기준 스냅숏을 복원한 DB에서 만든다. 같은 DB에서 다시 만들면 같은 파일이 나온다.

- 질의 계층이 읽는 허용 14테이블만 담는다. 열 정의·데이터만 넣고 외래 키·인덱스는 넣지 않는다.
- `res_users`는 질의 계층에 열린 열(id, partner_id, company_id, active, share)만 남긴다. 비밀번호·서명 등은 들어가지 않는다.
- 포털 공유 토큰(`access_token`)은 비운다.
- 나머지는 Odoo 데모 데이터(가상의 회사·인물)다. 공개 레포에 올리는 것을 2026-11-08에 정했다.
- `test_ci_eval.py`가 테이블 목록, `res_users` 열, 토큰이 비었는지를 검사한다.

스냅숏을 바꾸거나 허용 테이블을 바꾸면 덤프를 다시 만든다. 다시 만들지 않으면 `test_ci_eval.py`나 CI의 DB 테스트가 실패한다.
2026-11-08 기준 덤프는 `erp-20261103.zip`을 따로 복원한 DB에서 만든 것과 지금 로컬 DB에서 만든 것이 바이트까지 같았다.

## 20문항을 고른 기준

- 영역별 5문항(판매·구매·재고·회계).
- 2026-11-07~08 claude-haiku-5-5 OKF + 키워드 검색 8회 측정에서 8번 모두 맞힌 문항만 고른다. CI가 생성의 흔들림 때문에 실패하지 않게 하기 위해서다.
- 그중 행 범위가 걸리는 사용자(영업 사원 4명, 재고 담당)의 문항을 우선했다. admin 문항은 3개다.
- `min_correct`는 18이다. 회차 변동(±1~2)을 받아 주고, 그보다 크게 떨어지면 프롬프트·검색·guard 변경이 정확도를 깎은 것으로 본다.
- 문항 목록은 평가용이라 프롬프트에 쓰지 않는다(절대 규칙 4). CI는 점수만 낸다.
