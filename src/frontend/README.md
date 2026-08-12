# src/frontend/ — 코드설계팀 소유 (정적 프론트)

파일별 상세 역할·함수 목록은 **`docs/CODEBASE_MAP.md`** 참조.

## 작성규칙

1. **빌드 스텝 없음**: GitHub Pages에 그대로 배포 가능한 정적 파일만. 번들러·프레임워크·npm
   의존성 도입 금지 (도입하려면 부장 결재 선행).
   - `app/*.js`: 순수(비-module) `<script>` 태그로 전역 스코프를 공유하므로(ES 모듈 아님)
     `index.html`의 로드 순서가 곧 실행 순서이자 의존성 순서다. 현재 순서(2026-08 기준):

     ```
     i18n.js → utils.js → state.js → omakase.js → request-flow.js → band-filter.js →
     stage-graph.js → mode-switch.js → render-result.js → camelot-wheel.js → track-menu.js →
     youtube-player.js → track-edit.js → presets.js → song-picker.js →
     youtube-playlist-save.js → share-modal.js → playbar.js → main.js
     ```

     `app/i18n.js`가 항상 첫 번째(모든 파일이 참조하는 `t()`/`tArr()` 제공, 자기 자신은 아무
     것도 참조하지 않는 leaf), `app/utils.js`가 두 번째(`$`, `track`, `show`/`hide`/`toggle`,
     `prettyBand`, `makeBandIcon`, `BAND_ORDER` 등 다른 모든 파일이 참조하는 leaf 헬퍼),
     `app/main.js`가 항상 마지막(부트스트랩 — 나머지 전부가 정의된 뒤 실행돼야 함)이어야
     한다. 새 파일을 추가하거나 순서를 바꿀 땐 `index.html`의 스크립트 태그와
     `app/utils.js`/`app/i18n.js` 헤더 코멘트를 함께 확인할 것 — 순서를 잘못 두면 클래식
     스크립트는 ES 모듈과 달리 forward reference를 못 잡아줘서 `ReferenceError`로 조용히
     깨진다(과거 실제로 `BAND_ORDER`가 늦게 로드되는 파일로 옮겨져서 터진 사례 있음).
   - `style/*.css`: 컴포넌트별로 분리. `index.html`의 `<link>` 순서 = 캐스케이드 순서이므로
     (`style/base.css`의 색상 변수·리셋이 항상 먼저) 임의로 재배열하지 않는다.
2. 백엔드와의 계약은 **architecture.md 스키마 3** (`POST /api/setlist`, `GET /api/health`,
   `GET /api/bands`, `GET /api/songs`, `GET /api/setlist/status/{job_id}`, 공통 에러 포맷) —
   프론트에서 임의 필드를 기대하지 않는다.
3. API 키·시크릿을 프론트 코드에 넣지 않는다. Groq/OpenRouter 키는 백엔드 전용. 단, YouTube
   "내 계정에 저장" 기능(`app/youtube-playlist-save.js`)의 Google OAuth Client ID는 클라이언트
   사이드 흐름(GIS 토큰 클라이언트, client secret 없음)이라 공개돼도 안전하며 `index.html`의
   `window.GOOGLE_CLIENT_ID`로 노출돼 있다.
4. YouTube 재생은 iframe Player API로 순차 자동 전환(`app/youtube-player.js`). 실제 경과시간은
   `getDuration()`으로 추적한다 (엔진 사이징에는 사용 불가 — architecture.md §④-2).
5. umami 이벤트 계측을 유지한다(`app/utils.js`의 `track()` 래퍼 사용). 요청 대기 중 로딩
   애니메이션 표시 (§9 콜드스타트 UX, `app/request-flow.js`). AI 모드에서 백엔드가 202+`job_id`를
   반환하면 `GET /api/setlist/status/{job_id}`를 폴링하는 큐 UX도 이 파일이 담당한다.
6. 상태는 별도 스토어 없이 `app/state.js`의 top-level 전역(`picks`, `current`, `stageModel` 등)을
   다른 파일들이 직접 읽고 쓰는 구조다 — 새 전역을 추가할 땐 `state.js`에 선언하고, 필요한
   모듈에서만 참조한다.
