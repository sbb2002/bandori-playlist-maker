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

## B3. 플레이리스트 프리셋 저장 (로컬 캐시) ✅ 구현됨 (2026-07-12)

**사용자 제안(2026-07-11, 후순위)**: 생성된 플레이리스트를 **로컬 캐시(localStorage)** 에 저장하는
프리셋 기능. 형제 프로젝트 `bandori-song-sorter`가 랭크 진행률을 localStorage로 보존하는 방식과 동일.

**저장 대상**: 생성된 곡 목록(picks, 사용자 편집분 포함) + 모든 파라미터·내용
(prompt, params, stages, target_minutes, band/cover 필터, 에너지 아크 등) + 생성 시각·이름.

**UI(구상)**: 좌측 빈 영역에 프리셋 목록(불러오기/삭제/이름변경). 형제 프로젝트의 localStorage
스키마(`bandori-song-ranks-v1` 등) 관례 참고. 순수 프론트(백엔드 무관).

**메모**: 편집 기능(순서/제거/추가)이 이미 picks를 클라이언트 상태로 다루므로, 그 상태 스냅샷을
직렬화해 저장/복원하면 됨. 새 스키마 키(예: `setlist-presets-v1`).

---

## 베타 운영 시나리오 (docs/ref/user-opinion/2026-07-11-beta-service-scenario.md)

### ✅ 구현됨 (2026-07-11)
- **레이트리밋 우아한 처리**: OpenRouter 429/5xx 백오프 재시도(Retry-After 존중) + 지속 시 429
  `RATE_LIMITED` 안내. `OPENROUTER_MAX_RETRIES`.
- **콜드스타트 대기 UX**: 프론트 로딩 문구 위트 순환 + 8초 초과 시 '서버 깨우는 중' 강화.
- **운영 오류 알림**: `Notifier` 포트 + Telegram 어댑터(+Noop 폴백). 500/502 발생 시 개발자
  Telegram 알림(같은 유형 5분 스로틀, best-effort). `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`.

### B4. 실시간 대기 순번(큐 포지션) 🟡 보류
사용자에게 "당신은 N번째" 실시간 표시. 현재 동기 요청/응답 + 백오프로 자연 throttle만 함.
제대로 하려면 **비동기 잡 큐 + 상태 폴링/SSE**(요청→job_id 발급→진행 폴링) 아키텍처 필요.
파일럿 트래픽에선 재시도+위트 대기 UX로 충분 판단 → 부하 실측 후 도입 검토.

### B5. Keep-warm 셀프 핑 🟡 보류(트레이드오프)
활동 후 ~5분간 인스턴스를 깨어있게 유지(연속 요청 시 반복 콜드스타트 방지). 다만 무료 인스턴스-시간을
소모 → **월 무료 한도(항목 3)와 상충**. 활성 버스트 동안만 self-ping하는 정교한 구현 필요.
사용 패턴 데이터 확보 후 결정.

### B6. 외부 업타임 모니터(전체 다운 알림) 🟡 보류(자격증명)
무료 플랜 사용량 초과로 **서비스가 완전히 죽으면** 인앱 알림(B4 완료분)으론 못 잡음. 외부에서
`/api/health`를 감시하는 업타임 모니터 필요. 단, 잦은 핑은 인스턴스를 계속 깨워 무료시간을 소모하므로
저빈도(예: 일 1회, 콜드스타트 관용) + Render 사용량 이메일 병행 권장. (UptimeRobot 등 외부 서비스 또는
저빈도 GitHub Actions cron + `gh issue create`.)
