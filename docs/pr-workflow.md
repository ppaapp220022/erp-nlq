# PR 규칙

브랜치를 만들고, PR을 열고, 머지하기까지의 규칙이다. CLAUDE.md의 "작업 방식"은 이 문서를 줄인 것이다.

## 단위와 이름

- **작업 단위 하나 = 브랜치 하나 = PR 하나.** 기간(주차·마일스톤)으로 나누지 않는다.
- 브랜치 이름은 **영어**로 쓰고 `feat/`, `fix/`, `chore/`, `docs/`로 시작한다. 예: `feat/sql-guard`, `chore/db-snapshot`.
- 커밋과 PR의 제목·본문은 **한국어**로 쓴다. 제목은 `type: 한국어 요약` 형식이다(type은 영어).
- PR 본문은 [PR 템플릿](../.github/pull_request_template.md)을 따른다. "어떻게 확인했나"에는 실제로 실행한 명령과 결과를 적는다. 실행하지 못한 것은 못 했다고 쓴다.

## 레포 설정

| 설정 | 값 | 이유 |
|---|---|---|
| 머지 방식 | **스쿼시만** (머지 커밋·리베이스 머지 끔) | main에 PR 하나가 커밋 하나로 남는다. 이력이 일직선이다 |
| 스쿼시 커밋 제목·본문 | PR 제목·PR 본문 | PR 제목이 곧 main의 커밋 제목이다. 그래서 PR 제목을 `type: 한국어 요약`으로 쓴다 |
| 머지 후 브랜치 자동 삭제 | 켬 | 지운 브랜치를 기준으로 하던 PR은 GitHub이 main으로 옮겨 준다 |
| "Update branch" 버튼 | 켬 | main이 앞서 나가면 PR 화면에서 바로 따라잡는다 |
| 자동 머지 | 허용 | PR마다 켜 두면 필수 체크가 통과하는 순간 스쿼시 머지된다 |
| main 규칙(ruleset "main 보호") | PR로만 머지, `checks`·`ai-review` 필수, 일직선 이력, 강제 푸시·삭제 금지. 관리자는 우회 가능 | 관문을 거치지 않은 커밋이 main에 들어가지 않는다 |
| 외부 기여자 Actions 승인 | 외부 협업자 전부 승인 필요 | 퍼블릭 레포라 낯선 PR의 워크플로는 사람이 보고 나서 돈다 |

PR 브랜치 안의 커밋은 스쿼시되므로 작업 중에는 편하게 나눠 커밋한다.

### 외부 PR

레포가 퍼블릭이라 누구나 포크해서 PR을 올릴 수 있다. 외부 PR은 자동으로 머지되지 않는다.
- 자동 머지는 쓰기 권한이 있는 사람만 켤 수 있다.
- 포크 PR에는 시크릿이 전달되지 않아 `ai-review`가 실패하고(실패 시 닫힘), 필수 체크가 막는다.
- `restack`은 이 레포 안의 브랜치만 다룬다.
- 외부 PR을 받을 때는 diff를 직접 읽고, 필요하면 내 브랜치로 옮겨 다시 PR을 연다.

## 관문

main에 머지하려면 필수 체크 두 개가 통과해야 한다.

| 체크 | 내용 | 실패 조건 |
|---|---|---|
| `checks` | 셸·Python 문법, shellcheck, compose 설정, backend pytest (M3부터 우회 테스트, M6부터 평가 20문항) | 하나라도 실패 |
| `ai-review` | Claude가 [.github/review/prompt.md](../.github/review/prompt.md) 기준으로 검토한다. 지침은 기준 브랜치 버전을 쓴다 | blocking 1건 이상, 또는 판정 파일 없음(실패 시 닫힘) |

- `ai-review`는 Max 구독 토큰(시크릿 `CLAUDE_CODE_OAUTH_TOKEN`)으로 돈다. 만드는 법은 아래 "토큰 갱신".
- draft PR에서는 `ai-review`가 돌지 않는다. 작업 중에는 draft로 두고, 준비되면 Ready로 바꾼다.
- `ai-review`가 잘못 막았다고 판단되면, 이유를 PR 코멘트로 남기고 관리자 권한으로 우회 머지한다. 같은 오판이 반복되면 리뷰 지침을 고친다.

### 워크플로를 바꾸는 PR은 `ai-review`가 항상 실패한다

`claude-code-action`은 워크플로 파일이 **기본 브랜치(main)의 것과 똑같을 때만** 실행된다. 그래서 `.github/workflows/ai-review.yml`을 바꾸는 PR에서는 리뷰를 건너뛰고, 판정 파일이 없으니 `ai-review`가 실패한다.

이 동작은 의도한 대로다. PR이 관문 자체를 고쳐 스스로 통과하는 것을 막아 준다. 이런 PR은 다음 순서로 다룬다.
1. 본문에 무엇을 왜 바꾸는지 적는다.
2. `checks` 통과를 확인한다.
3. diff를 직접 읽고 관리자 권한으로 우회 머지한다.

워크플로가 main에 머지된 뒤 열려 있던 다른 PR은 main을 따라잡아야 리뷰가 돈다(아래 "main 따라잡기").

## main 따라잡기

PR 브랜치는 main 위로 **리베이스**한다. 머지 커밋으로 main을 끌어오지 않는다.

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease      # 남이 올린 커밋이 있으면 거부된다
```

푸시하면 `checks`와 `ai-review`가 다시 돈다. 리베이스는 그 브랜치의 PR이 열려 있는 동안만 한다. main은 절대 강제 푸시하지 않는다.

## 쌓인 PR (stacked)

앞 작업에 의존하는 작업은 앞 브랜치 위에 브랜치를 쌓고, PR의 기준 브랜치를 앞 브랜치로 둔다. 쌓기는 꼭 필요할 때만 하고, 2~3단을 넘기지 않는다.

**main 따라잡기:** 맨 위 브랜치에서 한 번만 리베이스하면 아래 브랜치들도 같이 옮겨진다.

```bash
git switch <맨 위 브랜치>
git rebase --update-refs origin/main
git push --force-with-lease origin <아래 브랜치> <맨 위 브랜치>
```

**머지:** 아래(main에 가까운 것)부터 스쿼시 머지된다. 모든 PR에 자동 머지를 켜 두면 아래 단계가 차례로 저절로 일어난다.
1. 아래 PR이 머지된다. 브랜치가 자동으로 지워지고, 바로 위 PR의 기준은 GitHub이 main으로 옮긴다.
2. 위 브랜치에는 아래 PR의 **원래 커밋**이 남아 있다. 스쿼시된 커밋과 내용은 같지만 커밋이 달라서, 그대로 두면 충돌한다. [restack 워크플로](../.github/workflows/restack.yml)가 원래 커밋을 떼어 내고 main 위로 옮겨 푸시한 뒤 PR에 코멘트를 남긴다.
3. 푸시로 `checks`·`ai-review`가 다시 돈다. 통과하면 자동 머지가 위 PR을 머지하고, 다시 1로 돌아간다.

restack이 충돌로 멈추면 PR 코멘트에 적힌 명령으로 직접 옮긴다. 손으로 할 때도 같다.

```bash
git fetch origin
git rebase --update-refs --onto origin/main <아래 PR의 마지막 커밋> <위 브랜치>
git push --force-with-lease origin <위 브랜치>
```

restack은 머지된 PR의 마지막 커밋을 품은 브랜치만 옮긴다. 아래 브랜치를 강제 푸시한 뒤 위 브랜치를 따라 옮기지 않았다면 대상에서 빠지므로, 쌓인 브랜치는 항상 `--update-refs`로 함께 옮긴다.

**자동 삭제를 쓰지 않고 브랜치를 직접 지우면** GitHub은 위 PR을 옮기지 않고 닫는다([troubleshooting](troubleshooting/2026-11-03-stacked-pr-closed-on-branch-delete.md)). 브랜치는 직접 지우지 않는다. 실수로 닫혔을 때는 다음 순서로 복구한다.
1. 지워진 기준 브랜치를 그 커밋으로 되살린다: `git push origin <커밋>:refs/heads/<브랜치>`
2. PR을 다시 연다: `gh pr reopen <번호>`
3. 기준을 main으로 바꾸고, main인 것을 확인한 뒤에만 되살린 브랜치를 지운다.

## 머지 권한

- Claude는 PR을 만들고, 자기 PR 브랜치를 리베이스·강제 푸시할 수 있다. **머지, 레포·브랜치 보호 설정 변경, 시크릿 관련 작업은 사용자 승인을 받은 뒤에만** 한다.
- PR에 자동 머지를 켜는 것(`gh pr merge <번호> --auto --squash`)이 곧 머지 승인이다. Claude는 사용자가 승인한 PR에만 켠다.
- `RESTACK_TOKEN`은 이 레포 하나만 대상으로 하는 fine-grained 토큰이다. 권한은 Contents·Pull requests 쓰기뿐이고 Workflows 권한은 없다. 그래서 워크플로 파일을 바꾸는 쌓인 PR은 restack이 푸시하지 못하고, 손으로 옮긴다.
- 시크릿 값은 사용자가 직접 넣는다. Claude는 값을 보지 않고 이름과 길이만 확인한다.

### 토큰 갱신

`CLAUDE_CODE_OAUTH_TOKEN`은 1년짜리다. 만료되면 `ai-review`가 비용 0으로 곧바로 실패한다. 채팅이 아닌 터미널 탭에서 직접 실행한다. 화면에서 토큰을 복사하지 않고 바로 시크릿에 넣는다.

```bash
stty cols 400; script -q "$TMPDIR/st.log" claude setup-token; stty cols "$(tput cols)"; T="$(sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' "$TMPDIR/st.log" | grep -ao 'sk-ant-oat[A-Za-z0-9_-]*' | tail -1)"; rm -f "$TMPDIR/st.log"; echo "길이 ${#T}"; [ ${#T} -gt 80 ] && printf %s "$T" | gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo ppaapp220022/erp-nlq; unset T
```

## 머지한 뒤

- `docs/plan.md`의 체크박스와 "현재 위치"가 머지한 내용과 맞는지 확인한다.
- 로컬을 정리한다: `git switch main && git pull --ff-only && git fetch --prune`, 그리고 머지된 로컬 브랜치를 지운다(`git branch -D`, 스쿼시라 `-d`는 거부된다).
