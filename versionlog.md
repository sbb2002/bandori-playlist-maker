# Version Log

이 저장소의 버전 이력을 기록한다. `git-rules.md`의 "버전 태깅(Tagging) 및 배포 규칙"에 따라
`epic/*`(Major) / `feature/*`(Minor) / `hotfix/*`(Patch) 브랜치가 `main`에 머지될 때마다
여기에 기록을 남긴다. 자동 태깅 CI(GitHub Actions)는 아직 구축되지 않았으므로, 현재는 이
로그가 유일한 버전 이력이며 수동으로 기록한다.

형식: `## vX.Y.Z — YYYY-MM-DD`, 요약, 관련 PR.

---

## v1.0.0 — 2026-07-13

베타 운영 중이던 저장소의 브랜치·버전 관리 정책(`git-rules.md`)을 정식화하면서 첫 버전을
공표한다. 이 시점의 `main`을 v1.0.0 기준선으로 삼는다.

- 기준 커밋: `c35deaa` (PR #10 머지 시점의 `main` HEAD)
- 포함 내용: 그 이전까지의 모든 베타 기능/수정 (PR #1 ~ #10)
- 관련 PR: [#11](https://github.com/sbb2002/bandori-playlist-maker/pull/11) `docs: git-rules.md
  브랜치 전략 전면 개편` — **아직 승인/머지되지 않음(OPEN)**. 이 versionlog.md 자체도 그 PR의
  일부로 올라가 있으므로, v1.0.0 공표는 PR #11이 병합되어야 공식 확정된다. 병합 전까지는
  잠정(provisional) 상태로 취급한다.
