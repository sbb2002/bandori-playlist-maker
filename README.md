# document-archive (bandori-playlist-maker)

> **브랜치 범위**: 아카이브 문서 전용 **단일 상시 재사용 브랜치**다(`data`·`tools`·`research`와
> 동일한 패턴). `archive/` 디렉터리만 다루며, **`main`에 다시 PR/머지되지 않는 완전히 분리된
> 별개 역사**다 — `origin`에 직접 commit·push만 한다(PR 없음). 상세 정책은 `main`의
> `git-rules.md` "document-archive" 절 참조.

## 문서 3분류(A/B/C)와의 관계

`main`(A/B 티어: 설계 철학·최상위 규칙, 개발자/방문자용 문서)과 달리, 이 브랜치는 **C 티어**
문서만 담는다 — "특정 시점 기록·다음 패치 아이디어"(작업 완료 후 다시 열어볼 일이 드문 스냅샷).

## archive/ 하위 구조

> **[2026-07-16 재편]** `archive/ref/` 래퍼를 없애고 `user-opinion/`·`verification/`을 루트로
> 끌어올림. `reports/`·`research/`는 `archive/last-papers/` 아래로 합침.

| 경로 | 용도 |
|---|---|
| `archive/user-opinion/` | 사용자가 세션에 전달한 참조 문서. **읽기 전용** — 사용자의 명시적 허락 없이 편집·삭제·이동·이름변경 금지(`main`의 `CLAUDE.md` "문서 취급 규칙" 참조) |
| `archive/verification/` | 검증용 참조 자료 |
| `archive/last-papers/reports/` | 작업 세션 보고서·설계 검토·인수인계 메모(날짜 접두어 `YYYY-MM-DD-...`) |
| `archive/last-papers/research/` | `research` 브랜치가 산출한 **완료된** 연구 보고서 `.md`의 최종 목적지(연구 진행 중 산출물은 `research` 브랜치 로컬에 둔다) |
| `archive/user_manual_pictures/` | 사용자 매뉴얼용 스크린샷 등 이미지 자산 |

## 읽기 참조 방법

이 브랜치는 `main` 워킹트리에 존재하지 않는다. 특정 파일만 볼 때:
```
git show document-archive:archive/<path>
```
여러 파일을 훑어볼 때는 워크트리로 펼친다:
```
git worktree add <임시경로> document-archive
```
어느 쪽도 `main` 히스토리에 영향을 주지 않는다.
