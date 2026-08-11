# archive/version/v2.2.0/ — 배포판 기준 사용 기능 로직·흐름도

`main`(태그 `v2.2.0`, PR #66 오마카세 + PR #67 테마토글까지 포함한 origin/main HEAD와 동일
내용)이 실제로 사용 중인 주요 로직 중, 짧지 않고 외부 API 호출 한 줄로 안 끝나는 것들만
골라 흐름도로 정리한다. `archive/last-papers/reports/`가 "특정 시점 기록·다음 패치
아이디어" 티어라면, 이 `version/<태그>/` 묶음은 "그 버전이 실제로 서비스하는 로직을 한
곳에 모은 스냅샷" 티어다 — 다음 버전에서 로직이 크게 바뀌면 새 `version/v<X.Y.Z>/` 폴더를
추가하고, 옛 폴더는 그대로 히스토리로 남긴다(수정하지 않음).

- [01-prompt-to-playlist-flow.md](01-prompt-to-playlist-flow.md) — 사용자 프롬프트 →
  플레이리스트 생성 전체 흐름(단일호출 Groq LLM 해석 + Stage A/B 선곡 알고리즘).
- [02-omakase-button-logic.md](02-omakase-button-logic.md) — 오마카세 버튼(시간대+날씨
  기반 프롬프트 자동 생성).
- [03-semi-autoloader-flow.md](03-semi-autoloader-flow.md) — semi-autoloader(신곡 반영
  파이프라인, `tools` 브랜치 — 배포판이 서빙하는 데이터의 생산 경로).
- [04-add-song-logic.md](04-add-song-logic.md) — 플레이리스트 편집 중 트랙 사이 곡 추가
  (밴드/곡 미니 브라우저).

플레이리스트 드래그 순서이동·곡 제거·에너지 그래프 드래그 편집·공유(YouTube 익명
재생목록)·YouTube 순차재생/자동스킵 등 나머지 기능은 로직이 짧거나 외부 API 호출 수준이라
별도 문서 없이 `README.md`의 "주요 기능" 표로 충분하다고 판단해 생략했다(2026-08-11,
저장소 소유자 판단).
