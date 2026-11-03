# ai-review가 0.4초 만에 비용 0으로 실패했다

- **상황:** PR #6에서 `claude-code-action`이 실행되자마자 `Claude execution failed: result is_error:true`로 끝났다. `duration_ms` 357~446, `total_cost_usd` 0, `modelUsage` 비어 있음. 디버그 모드로 다시 돌려도 오류 문구는 보이지 않았다(액션이 출력을 숨긴다).
- **원인:** API 크레딧 잔액이 부족했다. 키는 정상이었다. 로컬에서 같은 키로 Messages API를 직접 불러 확인했다: `invalid_request_error`, "credit balance is too low".
- **해결:** 리뷰는 API 키 대신 Max 구독 토큰(`claude setup-token`)을 쓰도록 바꿨다. 시크릿 `CLAUDE_CODE_OAUTH_TOKEN`, 워크플로 입력 `claude_code_oauth_token`.
- **배운 점:**
  - 비용 0으로 곧바로 끝나면 프롬프트가 아니라 인증·결제 문제다. 액션 로그만 보지 말고 같은 키로 API를 직접 불러 본다.
  - 구독 토큰은 Claude Code용이다. 앱의 `generate()`와 평가는 Console 크레딧이 있는 API 키를 쓴다. M2를 시작할 때 소액 충전하고 자동 충전은 끈다.
