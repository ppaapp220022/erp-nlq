# PR 규칙

브랜치를 만들고, PR을 열고, 머지하기까지의 규칙이다. CLAUDE.md의 "작업 방식"은 이 문서를 줄인 것이다.

## 단위와 이름

- **작업 단위 하나 = 브랜치 하나 = PR 하나.** 기간(주차·마일스톤)으로 나누지 않는다.
- 브랜치 이름은 **영어**로 쓰고 `feat/`, `fix/`, `chore/`, `docs/`로 시작한다. 예: `feat/sql-guard`, `chore/db-snapshot`.
- 커밋과 PR의 제목·본문은 **한국어**로 쓴다. 제목은 `type: 한국어 요약` 형식이다(type은 영어).
- PR 본문은 [PR 템플릿](../.github/pull_request_template.md)을 따른다. "어떻게 확인했나"에는 실제로 실행한 명령과 결과를 적는다. 실행하지 못한 것은 못 했다고 쓴다.

## 관문

main에 머지하려면 필수 체크 두 개가 통과해야 한다.

| 체크 | 내용 | 실패 조건 |
|---|---|---|
| `checks` | 셸·Python 문법, shellcheck, compose 설정, backend pytest (M3부터 우회 테스트, M6부터 평가 20문항) | 하나라도 실패 |
| `ai-review` | Claude가 [.github/review/prompt.md](../.github/review/prompt.md) 기준으로 검토한다. 지침은 기준 브랜치 버전을 쓴다 | blocking 1건 이상, 또는 판정 파일 없음(실패 시 닫힘) |

- draft PR에서는 `ai-review`가 돌지 않는다. 리뷰 비용을 아끼려면 작업 중에는 draft로 두고, 준비되면 Ready로 바꾼다.
- `ai-review`가 잘못 막았다고 판단되면, 이유를 PR 코멘트로 남기고 관리자 권한으로 우회 머지한다. 같은 오판이 반복되면 리뷰 지침을 고친다.

### 워크플로를 바꾸는 PR은 `ai-review`가 항상 실패한다

`claude-code-action`은 워크플로 파일이 **기본 브랜치(main)의 것과 똑같을 때만** 실행된다. 그래서 `.github/workflows/ai-review.yml`을 바꾸거나 처음 추가하는 PR에서는 Claude가 리뷰를 건너뛰고, 판정 파일이 없으니 `ai-review`가 실패한다.

이 동작은 의도한 대로다. PR이 관문 자체를 고쳐 스스로 통과하는 것을 막아 준다. 이런 PR은 다음 순서로 다룬다.
1. 본문에 무엇을 왜 바꾸는지 적는다.
2. `checks` 통과를 확인한다.
3. diff를 직접 읽고 관리자 권한으로 우회 머지한다.

## 쌓인 PR (stacked)

앞 작업에 의존하는 작업은 앞 브랜치 위에 브랜치를 쌓는다. PR의 기준 브랜치를 앞 브랜치로 둔다.

**머지 순서와 방식**
1. 아래(main에 가까운 것)부터 하나씩 머지한다.
2. 방식은 **머지 커밋**이다. 스쿼시나 리베이스로 합치면 위에 쌓인 PR들과 커밋이 달라져 충돌한다.
3. **머지하기 전에 바로 위 PR의 기준 브랜치를 main으로 먼저 바꾼다.** 그다음 머지하고 브랜치를 지운다. 기준 브랜치가 지워지면 GitHub은 그 위 PR을 main으로 옮기지 않고 **닫아 버린다**([troubleshooting](troubleshooting/2026-11-03-stacked-pr-closed-on-branch-delete.md)).

```bash
gh api -X PATCH repos/ppaapp220022/erp-nlq/pulls/<위 PR> -f base=main   # 1. 위 PR 기준을 main으로
gh pr view <위 PR> --json baseRefName                                      # 2. main인지 확인
gh pr merge <이 PR> --merge --delete-branch                                 # 3. 머지와 브랜치 삭제
```

**실수로 닫혔을 때 복구**
1. 지워진 기준 브랜치를 그 커밋으로 되살린다: `git push origin <커밋>:refs/heads/<브랜치>`
2. PR을 다시 연다: `gh pr reopen <번호>`
3. 기준을 main으로 바꾸고, main인 것을 확인한다.
4. 확인한 뒤에만 되살린 브랜치를 지운다.

## 머지 권한

- Claude는 PR을 만들 수 있다. **머지, 브랜치 보호 변경, 시크릿 관련 작업은 사용자 승인을 받은 뒤에만** 한다.
- API 키 같은 시크릿 값은 사용자가 `gh secret set`으로 직접 넣는다. Claude는 값을 보지 않고 이름만 확인한다.

## 머지한 뒤

- `docs/plan.md`의 체크박스와 "현재 위치"가 머지한 내용과 맞는지 확인한다.
- 로컬을 정리한다: `git fetch --prune`, 그리고 지워진 원격 브랜치를 가리키는 로컬 브랜치를 삭제한다.
