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
