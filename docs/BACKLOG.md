# 포스트-파일럿 백로그

베타 서비스 중 추가할 기능. 우선순위·의존성 명시. (파일럿 필수 범위는 PRD §4.)

---

## B1. YouTube 계정 저장형 재생목록 — 제목·공개 설정 (OAuth + Data API) 🔴 사용자 요청

**현상(2026-07-11 사용자 보고)**: 'YouTube 재생목록 만들기'가 익명 `watch_videos?video_ids=…`로
임시 재생목록을 연다. 결과가 **"Untitled List" · 일부공개(임시)** 로 뜬다.

**요청**: 제목 = summary card 내용, **누구나 볼 수 있게 공개**, 저장·공유 가능.

**기술적 사실(중요)**: 위 요구(커스텀 제목 + 공개 + 계정 저장)는 익명 `watch_videos`로 **불가능**하다.
YouTube Data API v3 `playlists.insert`(`snippet.title`, `status.privacyStatus="public"`) +
`playlistItems.insert`가 필요하고, 이는 **OAuth 2.0 인증**(사용자 유튜브 계정 접근 동의)을 요구한다.
→ Google Cloud 프로젝트 · OAuth 동의화면 · 클라이언트 자격증명 · (백엔드 or gapi) 인증 플로우 필요.
PRD는 이를 파일럿 범위 밖으로 명시(§5, "OAuth + Data API 필요"). 클린아키텍처상 **공유 포트 +
YouTube 어댑터** 신설로 처리(무드 포트와 별개).

**작업 개요**:
- (a) Google OAuth 클라이언트(웹) + 동의화면. 스코프 `youtube` 또는 `youtube.force-ssl`.
- (b) 프론트: 로그인 → 토큰 획득. 또는 백엔드 OAuth 콜백(리프레시 토큰 보관).
- (c) `playlists.insert`(제목=summary, privacy=public) → `playlistItems.insert` 곡별 →
  생성된 `playlistId`로 공유 URL(`https://www.youtube.com/playlist?list=…`).
- (d) 실패/미인증 시 현재 익명 `watch_videos`로 폴백.

## B2. 공유 결과 팝업 UX 🟡 (B1 없이도 부분 구현 가능)

**사용자 제안**: 'YouTube 재생목록 만들기' 클릭 시 작은 팝업:
- "플레이리스트가 생성되었어요" 안내
- 재생목록 URL + **복사 버튼**
- **유튜브에서 직접 듣기** 버튼

**메모**: B1(OAuth) 완료 전에도, **현재 공유 가능한 URL**로 팝업 자체는 구현 가능(제목·공개는
B1 이후 제대로). 즉 UX 껍데기를 먼저 붙이고, 내부 URL 생성만 B1에서 교체하는 순서가 자연스럽다.

## B3. 플레이리스트 프리셋 저장 (로컬 캐시) 🟢 후순위 (사용자 지시: 작성만)

**사용자 제안(2026-07-11, 후순위)**: 생성된 플레이리스트를 **로컬 캐시(localStorage)** 에 저장하는
프리셋 기능. 형제 프로젝트 `bandori-song-sorter`가 랭크 진행률을 localStorage로 보존하는 방식과 동일.

**저장 대상**: 생성된 곡 목록(picks, 사용자 편집분 포함) + 모든 파라미터·내용
(prompt, params, stages, target_minutes, band/cover 필터, 에너지 아크 등) + 생성 시각·이름.

**UI(구상)**: 좌측 빈 영역에 프리셋 목록(불러오기/삭제/이름변경). 형제 프로젝트의 localStorage
스키마(`bandori-song-ranks-v1` 등) 관례 참고. 순수 프론트(백엔드 무관).

**메모**: 편집 기능(순서/제거/추가)이 이미 picks를 클라이언트 상태로 다루므로, 그 상태 스냅샷을
직렬화해 저장/복원하면 됨. 새 스키마 키(예: `setlist-presets-v1`).
