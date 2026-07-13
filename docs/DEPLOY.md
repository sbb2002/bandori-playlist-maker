# 배포 가이드 (베타)

정적 프론트(**GitHub Pages**) + API 키를 쥔 백엔드(**Render**) 구성. PRD §8 아키텍처.

| 레이어 | 호스팅 | URL |
|---|---|---|
| 프론트 | GitHub Pages (`src/frontend`) | `https://sbb2002.github.io/bandori-playlist-maker/` |
| 백엔드 | Render (FastAPI, 무료 플랜) | `https://bandori-playlist-maker.onrender.com` |

두 URL은 이미 코드에 서로 연결돼 있음:
- 프론트 → 백엔드: `src/frontend/index.html`의 `SETLIST_API_BASE` (localhost면 로컬, 그 외면 Render).
- 백엔드 → 프론트(CORS): `render.yaml`의 `FRONTEND_ORIGIN=https://sbb2002.github.io`.

> Render/Pages가 다른 URL을 주면 위 두 곳만 고치면 됨.

---

## 1. 백엔드 — Render (Blueprint)

1. Render 대시보드 → **New → Blueprint** → 이 GitHub 리포 연결.
   `render.yaml`을 읽어 서비스(`bandori-playlist-maker`)를 자동 구성한다.
2. **환경변수 `OPENROUTER_API_KEY` 입력** (시크릿이라 커밋 안 됨, `sync: false`).
   대시보드의 해당 서비스 → Environment → 값 입력.
   - 키를 넣으면 OpenRouter(모델 `nemotron:free`)로 동작.
   - **키 없이도 앱은 뜬다** — stub(오프라인 휴리스틱)로 폴백(무드 해석 품질만 낮아짐).
3. 첫 배포 후 확인: `https://bandori-playlist-maker.onrender.com/api/health` → `{"status":"ok"}`.
4. 서비스 URL이 위와 다르면(이름 중복 등) → `src/frontend/index.html`의 배포 URL 한 줄 수정.

메모
- `region: singapore` (KR 지연↓). 미지원이면 `render.yaml`에서 `oregon` 등으로 변경.
- 무료 플랜은 15분 유휴 후 슬립 → 첫 요청 cold start(~50s). 프론트 로딩 문구가 안내함.
- `autoDeploy: true` — main 푸시 시 자동 재배포.

## 2. 프론트 — GitHub Pages (Actions)

1. 리포 **Settings → Pages → Source = "GitHub Actions"** 로 설정(최초 1회).
2. `.github/workflows/pages.yml`가 `src/frontend`를 Pages로 배포.
   `src/frontend/**` 변경 푸시 시 자동 실행. 최초/강제 실행은 Actions 탭에서 **Run workflow**.
3. 배포 후: `https://sbb2002.github.io/bandori-playlist-maker/` 접속.
4. Pages 오리진이 다르면 → `render.yaml`의 `FRONTEND_ORIGIN` 수정 후 재배포.

> 프론트는 상대경로(`assets/…`, `app.js`)만 써서 서브경로(`/bandori-playlist-maker/`) 게시에도 정상 동작.

## 3. 최종 점검

- [ ] `/api/health` 200 OK
- [ ] Pages 사이트 로드 → 요청 입력 → 플레이리스트 생성(첫 요청은 cold start로 느릴 수 있음)
- [ ] 곡 추가 팝업의 밴드 아이콘 표시(`assets/bands/*.png`)
- [ ] 브라우저 콘솔에 CORS 에러 없음(있으면 `FRONTEND_ORIGIN` 오리진 확인)

## 4. 운영 메모

- **모델 교체**: Render 환경변수 `OPENROUTER_MODEL` 한 줄. (현재 `nemotron:free`)
- **계측(umami)**: `index.html`의 umami `<script>` 주석 해제 + website-id 입력 시 활성.
  이벤트: `playlist_created` · `song_advance` · `playlist_half_played` · `playlist_shared` · `song_added`.
- **비밀값**: `OPENROUTER_API_KEY`는 절대 커밋 금지(`.gitignore`가 `.env` 차단). Render 시크릿으로만.

## 5. 트래픽 급증·오류 대비 (운영 하드닝)

배포 문서: `docs/ref/user-opinion/2026-07-11-beta-service-scenario.md`.

**레이트리밋(공개 직후 동시 요청 폭주)**
- OpenRouter 429/5xx는 **지수 백오프+지터로 재시도**(`OPENROUTER_MAX_RETRIES`, 기본 2). Retry-After 헤더 존중.
- 재시도 소진 후에도 429면 **429 `RATE_LIMITED`** + "지금 요청이 많아요…" 안내(프론트 표시).
- 세마포어 선블로킹은 동기 스레드풀을 고갈시켜 헬스체크를 위협하므로 쓰지 않음(재시도로 자연 throttle).

**콜드스타트(무료 슬립 후 첫 응답 ~수십초)**
- 프론트 로딩 문구가 **위트있게 순환** + 8초 초과 시 "서버 깨우는 중… 🥱" 안내로 강화(자동, 설정 불필요).

**운영 오류 알림(Telegram) — 선택**
- 사용자 요청 처리 중 500(내부)·502(LLM) 발생 시 개발자 Telegram으로 알림(같은 유형은 5분 1회 스로틀).
- 설정(둘 다 필요, 없으면 자동 비활성):
  1. Telegram에서 **@BotFather** → `/newbot` → **봇 토큰** 발급.
  2. 그 봇과 대화 시작 후 `https://api.telegram.org/bot<토큰>/getUpdates` 로 내 **chat id** 확인.
  3. Render 환경변수 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`(시크릿) 입력.
- 미설정 시 Noop(알림 없음) — 앱 동작엔 영향 없음.
- 채널을 GitHub Issues로 바꾸려면 `Notifier` 포트에 GitHub 어댑터를 추가(포트 교체 1곳). 백로그 참고.

**무료 플랜 전체 다운(월 사용량 초과·슬립)**: 앱이 죽은 상태라 인앱 알림으론 못 잡음 → 외부 업타임 모니터
필요(백로그 B6). Render도 사용량 이메일을 보냄.

## 6. Google OAuth(YouTube 재생목록 저장)

사용자가 "내 재생목록에 넣기"를 누르면 프론트가 Google Identity Services로 access token을 받아
브라우저에서 직접 YouTube Data API v3(`playlists.insert`, `playlistItems.insert`)를 호출한다.
백엔드는 관여하지 않음(client secret 없음, refresh token 저장 없음, 토큰은 세션 메모리에만 존재).

**최초 설정(1회, Google Cloud Console)**
1. https://console.cloud.google.com → 프로젝트 생성 → "YouTube Data API v3" 사용 설정.
2. OAuth 동의 화면(외부) 구성 → 스코프에 `youtube.force-ssl` 추가 → 테스트 사용자 등록.
3. 사용자 인증 정보 → OAuth 클라이언트 ID(웹 애플리케이션) 발급.
   - 승인된 자바스크립트 원본: `https://sbb2002.github.io`, `http://localhost:5500`.
   - 리디렉션 URI 불필요(팝업 기반 토큰 플로우).
4. 발급된 Client ID를 `src/frontend/index.html`의 `window.GOOGLE_CLIENT_ID`에 입력 후 배포.

**운영 메모(중요)**
- 일일 할당량 10,000유닛은 이 Cloud 프로젝트의 전체 사용자 합산이다. 17곡 재생목록 1개는
  약 900유닛(재생목록 생성 50 + 곡당 50). 하루 약 11회가 사실상 상한 — 초과 시 "재생목록을
  만들지 못했어요" 에러가 뜬다. 늘리려면 Cloud Console에서 할당량 증가를 요청한다.
- `youtube.force-ssl`은 민감 스코프라 OAuth 앱이 미인증 상태에서는 테스트 사용자 100명까지만
  로그인 가능하고, 그 외 사용자에겐 "확인되지 않은 앱" 경고가 뜬다. 베타 사용자가 100명을
  넘거나 경고 없이 공개하려면 Google OAuth 앱 인증(verification) 심사를 신청해야 한다
  (수일에서 수주 소요, 개인정보처리방침 URL 등 필요).
- Client ID는 시크릿이 아니므로 커밋해도 무방하다(공개 GitHub Pages 소스에도 그대로 노출된다).

**Google 인증(verification) 심사 신청 — 제출 필드 초안**

동의 화면이 "프로덕션(In production)"으로 게시된 뒤, 경고 화면 없이 모든 사용자가 쓰게 하려면
아래 필드를 채워 심사를 신청한다. Cloud Console → API 및 서비스 → OAuth 동의 화면 → "확인 준비"
에서 입력.

| 필드 | 값(초안) |
|---|---|
| 앱 이름 | Bangdream Playlist Maker (Bandori Playlist Maker) |
| 앱 로고 | `docs/user_manual_pictures/logo-yumemita.png` 등 정사각형 로고 업로드(120x120px 권장) |
| 앱 홈페이지 | `https://sbb2002.github.io/bandori-playlist-maker/` |
| 개인정보처리방침 링크 | `https://sbb2002.github.io/bandori-playlist-maker/privacy.html` |
| 승인된 도메인 | `github.io` (Search Console로 `sbb2002.github.io` 소유권 인증 필요) |
| 개발자 연락처 이메일 | sbb4113@gmail.com |

**스코프 사용 근거(justification) — `youtube.force-ssl` 입력란에 붙여넣을 텍스트**

한국어(제출은 영어 권장, 아래 영문 사용):

> 이 앱은 자연어 요청을 밴드리(BanG Dream!) 음악 플레이리스트로 변환하는 비상업적 팬 프로젝트다.
> "내 재생목록에 넣기" 버튼을 눌렀을 때만 스코프를 요청하며, 목적은 딱 하나 — 생성된 곡 순서
> 그대로 사용자 본인의 YouTube 계정에 새 재생목록을 만들고 곡을 추가하는 것뿐이다. 채널 정보
> 열람, 구독 관리, 기존 영상 수정 등 다른 어떤 동작도 하지 않는다. 더 좁은 스코프(`youtube.readonly`
> 등)로는 재생목록 생성·곡 추가(쓰기 동작)가 불가능해 `youtube.force-ssl`이 필요한 최소 스코프다.

영문(그대로 제출용):

> This app is a non-commercial fan project that turns a natural-language request into a BanG Dream!
> music playlist. The scope is only requested when the user clicks "Save to my playlist," and is used
> for exactly one purpose: creating a new playlist in the user's own YouTube account and adding the
> generated songs to it, in order. The app never reads channel info, manages subscriptions, or
> modifies existing videos. A read-only scope cannot perform the write operations (playlist creation,
> item insertion) this feature requires, so `youtube.force-ssl` is the minimum scope needed.

**심사 제출 시 함께 요구되는 것**
- 데모 영상(YouTube "목록에 표시 안 함" 업로드): 실제 배포 사이트에서 로그인 → **동의 화면(요청
  스코프 목록이 보이는 화면) 노출** → 동의 → 실제 YouTube 계정(youtube.com)에서 생성된 재생목록
  확인까지 전 과정이 끊기지 않고 담겨야 한다. localhost 녹화나 동의 화면 생략은 반려 사유가 된다.
- 위 표의 홈페이지·개인정보처리방침 URL이 실제로 접근 가능해야 한다(이 PR이 `main`에 머지되어
  GitHub Pages에 배포된 뒤에 신청할 것).
