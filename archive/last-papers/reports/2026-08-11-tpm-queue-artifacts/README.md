# 2026-08-11 — TPM 큐잉(비동기 잡+폴링) 동작 재현 아티팩트 2건

> **상태: 세션 산출물 보관.** PR #65(`patch/setlist-queue-status` — `app/jobs.py` JobStore,
> `queue_position`/`estimated_wait_seconds`, 큐 정원 초과 429) 구현 직후 "실제로 어떻게 큐에
> 실리고 정지되는지" 확인하려고 만든 인터랙티브 HTML 2개. 코드는 아니라서 `main`으로 안 가고
> 여기(C 티어: 특정 시점 기록)에 둔다. 원본은 claude.ai 아티팩트로도 게시돼 있었음(세션 한정
> URL이라 만료 가능 — 이 폴더의 사본이 유일한 영구 보관본).

## 01-tpm-queue-monitor.html

백엔드 로그·메커니즘 관점. 실제 로컬 세션에서 curl로 잡은 실측 로그(요청 3건 연타 →
`queue_position` 0/1/2, `estimated_wait_seconds`가 13.8초→33.2초로 역전되는 근사치 특성까지
그대로 옮김)를 터미널 트랜스크립트로 재현하고, 그 아래 같은 `TokenBucketLimiter` 알고리즘을
재생하는 인터랙티브 시뮬레이션(TPM 게이지 소진/충전, 카드가 QUEUED→RUNNING→DONE으로 넘어가는
과정)을 붙였다.

## 02-queue-ui-preview.html

사용자 관점. `src/frontend/style.css`의 실제 디자인 토큰(`--bg`, `--card`, `--accent: #7c6cff`,
spinner 등)을 그대로 옮긴 폰 프레임 안에서, `app.js`의 `setQueueWaitMessage()`가 실제로
만드는 문자열("내 앞에 N명 대기 중. 약 M초…")로 로딩 화면이 갱신되는 과정을 재생한다. 오른쪽
타임라인이 각 단계를 대응 API 호출(`POST /api/setlist` → `GET /api/setlist/status/{job_id}`
폴링)에 연결해 보여준다.

## 참고

- 관련 PR: [#65](https://github.com/sbb2002/bandori-playlist-maker/pull/65)
- 두 파일 다 완전 self-contained(외부 리소스 없음) — 로컬에서 그냥 브라우저로 열어도 된다.
