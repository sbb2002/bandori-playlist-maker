# src/frontend/ — 코드설계팀 소유 (정적 프론트)

## 작성규칙

1. **빌드 스텝 없음**: GitHub Pages에 그대로 배포 가능한 정적 파일만. 번들러·프레임워크·npm
   의존성 도입 금지 (도입하려면 부장 결재 선행).
   - `app/*.js`: 예전엔 단일 `app.js`였으나 기능별로 분리했다. 순수(비-module) `<script>`
     태그로 전역 스코프를 공유하므로(ES 모듈 아님) `index.html`의 로드 순서가 곧 실행
     순서이자 의존성 순서 — `app/utils.js`가 항상 첫 번째(다른 모든 파일이 참조하는 leaf
     헬퍼: `$`, `track`, `show`/`hide`/`toggle`, `prettyBand`, `makeBandIcon`, `BAND_ORDER` 등),
     `app/main.js`가 항상 마지막(부트스트랩 — 나머지 전부가 정의된 뒤 실행돼야 함)이어야
     한다. 새 파일을 추가하거나 순서를 바꿀 땐 `index.html`의 스크립트 태그 주석과
     `app/utils.js` 헤더 코멘트를 함께 확인할 것 — 순서를 잘못 두면 클래식 스크립트는
     ES 모듈과 달리 forward reference를 못 잡아줘서 `ReferenceError`로 조용히 깨진다.
   - `style/*.css`: 컴포넌트별로 분리. `index.html`의 `<link>` 순서 = 캐스케이드 순서이므로
     (예: `style/base.css`의 색상 변수가 먼저 정의돼야 함) 임의로 재배열하지 않는다.
2. 백엔드와의 계약은 **architecture.md 스키마 3** (`POST /api/setlist`, `GET /api/health`,
   공통 에러 포맷) — 프론트에서 임의 필드를 기대하지 않는다.
3. API 키·시크릿을 프론트 코드에 넣지 않는다 (OpenRouter 키는 백엔드 전용).
4. YouTube 재생은 iframe Player API로 순차 자동 전환. 실제 경과시간은 `getDuration()`으로
   추적한다 (엔진 사이징에는 사용 불가 — architecture.md §④-2).
5. umami 이벤트 3종 계측을 유지한다. 요청 대기 중 로딩 애니메이션 표시 (§9 콜드스타트 UX).
