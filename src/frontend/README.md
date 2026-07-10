# src/frontend/ — 코드설계팀 소유 (정적 프론트)

## 작성규칙

1. **빌드 스텝 없음**: GitHub Pages에 그대로 배포 가능한 정적 3파일(`index.html`, `app.js`,
   `style.css`)만. 번들러·프레임워크·npm 의존성 도입 금지 (도입하려면 부장 결재 선행).
2. 백엔드와의 계약은 **architecture.md 스키마 3** (`POST /api/setlist`, `GET /api/health`,
   공통 에러 포맷) — 프론트에서 임의 필드를 기대하지 않는다.
3. API 키·시크릿을 프론트 코드에 넣지 않는다 (OpenRouter 키는 백엔드 전용).
4. YouTube 재생은 iframe Player API로 순차 자동 전환. 실제 경과시간은 `getDuration()`으로
   추적한다 (엔진 사이징에는 사용 불가 — architecture.md §④-2).
5. umami 이벤트 3종 계측을 유지한다. 요청 대기 중 로딩 애니메이션 표시 (§9 콜드스타트 UX).
