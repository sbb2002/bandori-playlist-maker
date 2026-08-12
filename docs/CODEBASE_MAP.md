# 코드베이스 맵 (파일별 기능 요약)

작성: 2026-08-12 · `src/backend`·`src/frontend`의 현재 코드를 직접 읽고 정리한 스냅샷.

이 문서의 위치: `docs/architecture.md`는 **파일럿 설계 시점(2026-07-10)에 동결된** 원칙/계약
문서다. 이 문서(`CODEBASE_MAP.md`)는 반대로 **지금 코드가 실제로 어떻게 생겼는지**를 파일
단위로 훑는 참고 지도이며, 코드가 바뀌면 이 문서도 낡는다 — 최신 사실은 항상 코드가 우선한다.
설계 원칙·팀 규칙은 `docs/architecture.md`와 각 폴더 `README.md`를 따른다.

---

## 1. 전체 구조 한눈에

```
src/
├─ backend/app/          FastAPI 백엔드 (헥사고날 구조)
│  ├─ domain/            순수 함수 계층 — 선곡 엔진의 핵심
│  ├─ ports/              Protocol 인터페이스 (LLM, 임베딩, 알림)
│  ├─ adapters/           ports 구현체 (Groq/OpenRouter/Stub, rate limiter, Telegram)
│  ├─ api/                라우트 + pydantic DTO
│  ├─ repo/                데이터 로딩 (CSV, 원격 fetch, 일본어 음차)
│  ├─ main.py             composition root
│  └─ jobs.py             인메모리 비동기 잡 큐
└─ frontend/              빌드 스텝 없는 정적 SPA (classic script, 전역 공유)
   ├─ app/*.js             기능별 분리 스크립트 (18개, 로드 순서=의존 순서)
   └─ style/*.css          컴포넌트별 CSS (로드 순서=캐스케이드 순서)
```

의존 방향(백엔드): `api → domain ← ports ← adapters/repo`, `main.py`가 조립한다. 프론트는
빌드 도구 없이 `index.html`의 `<script>` 순서가 곧 모듈 의존 그래프다.

---

## 2. 백엔드 (`src/backend/app/`)

### 2.1 domain/ — 순수 계층 (외부 의존 없음, LLM 없이 단위 테스트 가능)

| 파일 | 역할 |
|---|---|
| `models.py` | `Song`(곡 카탈로그 1행 — 에너지·6종 오디오 피처·경계텐션·가사임베딩·검색용 음차 필드), `MoodParameters`(LLM 해석 결과 스키마), `Stage`/`StageSpec`, `PickReason`(선곡 사유), `Pick`, `Setlist`(엔진 출력), `NoSetlistError`. 2026-08-11에 옛 밝기(`mode_score`/`shape`) 축을 제거하고 에너지+6피처 통합 거리로 단일화했다. |
| `energy.py` | 단계별 에너지 목표 선형보간(`stage_energy_targets`), 총 곡 수·단계별 곡 수 산정(`total_song_count`/`distribute_counts`/`distribute_counts_by_weights`), 곡 단위로 부드럽게 이어지는 목표값 보간(`continuous_slot_targets` — 그래프는 매끄러운데 실제 매칭은 계단식이던 버그의 수정). |
| `harmonic.py` | `src/scripts/data/camelot.py`의 `is_adjacent()`를 감싸는 얇은 래퍼. 하모닉 호환 판정(`is_compatible`)과 UI용 라벨(`harmonic_label`: seed/same/adjacent/non_harmonic). |
| `selection.py` | **핵심 선곡 엔진** `build_setlist()`. 2단계 설계: (A) SELECT — 단계별 무드/에너지 타겟에 맞는 곡을 하드 선별(밴드락 필터→거리 계산→버킷화→가사 유사도 상위 50%→랜덤), (B) SEQUENCE — 경계 연속성(전곡 아웃트로 에너지 vs 다음곡 인트로 에너지) + 하모닉 페널티 기반 그리디 체인 + 국소 2-opt 정련. 상수는 전부 "실사용 피드백으로 튜닝 예정" 주석이 붙어 있는 프로토타입 값. |
| `tags.py` | LLM이 태그를 충분히 안 주면 무드 파라미터에서 결정론적으로 태그를 보강(`derive_tags`/`ensure_min_tags`). |

### 2.2 ports/ — Protocol 인터페이스

| 파일 | 역할 |
|---|---|
| `mood_port.py` | `MoodInterpreter` Protocol(`interpret()`), 예외 계층 `MoodInterpretationError`/`LLMUpstreamError`/`LLMRateLimitError`. |
| `embedding_port.py` | `TextEmbedder` Protocol — L2-정규화된 384차원 벡터 반환 계약. |
| `notify_port.py` | `Notifier` Protocol(`async notify()`, 절대 예외를 던지면 안 됨) + 기본 `NoopNotifier`. |

### 2.3 adapters/ — ports 구현체

| 파일 | 역할 |
|---|---|
| `groq_adapter.py` | **현재 프로덕션 기본** `MoodInterpreter`. 단일 LLM 호출, `prompt.py`로 프롬프트 생성/파싱 위임, `rate_limiter.py`의 TPM 토큰버킷을 호출 전에 선점(`acquire`)해 큐잉을 HTTP 요청 밖으로 뺀다. 429/5xx는 지수 백오프+지터로 재시도. |
| `groq_multistage_adapter.py` | 실험적 대안. 1번의 통합 호출 대신 **4번의 순차 호출**(총 분량→단계별 분량/무드키워드→단계별 에너지→요약문)로 나눠 JSON 파싱 리스크를 줄인다. TPM 리밋·6종 오디오 피처(`stage_params`)·다국어 미지원 — 아직 기본 경로 아님, `MOOD_INTERPRETER=groq_multistage`로만 켜짐. |
| `openrouter_adapter.py` | 예비/레거시 대안 어댑터(구조는 `groq_adapter.py`와 거의 동일, TPM 사전 레이트리밋만 없음). **주의**: `.env.example`은 이 어댑터를 여전히 "필수" 경로로 안내하지만 `main.py._build_interpreter()`는 현재 이 어댑터로 분기하지 않는다 — 실제 기본은 Groq. |
| `stub_adapter.py` | 키 미설정 시 오프라인 폴백. 키워드 휴리스틱만으로 밝기/에너지/분량을 추정. 응답 요약 끝에 `"(이 문구는 stub입니다.)"`를 붙여 프로덕션 오폴백을 `/api/health`와 함께 감지할 수 있게 한다. |
| `embedding_adapter.py` | `SentenceTransformerEmbedder` — `intfloat/multilingual-e5-small`을 지연 로딩 싱글턴으로 감싼 `TextEmbedder` 구현. 가사 인상(impression) 텍스트와 곡의 사전계산 임베딩(`lyric_impressions.json`) 코사인 유사도 비교에 쓰인다. |
| `rate_limiter.py` | `TokenBucketLimiter` — 스레드 세이프 토큰버킷. `cost=1`이면 RPM 리밋, 가변 비용(`groq_adapter`가 추정 토큰 수를 넘김)이면 TPM 리밋으로 동작. |
| `telegram_notifier.py` | `TelegramNotifier` — 에러 알림을 텔레그램으로 전송, 같은 제목의 알림은 5분 스로틀(장애 폭주 시 알림 폭탄 방지). |
| `prompt.py` | `groq_adapter`/`openrouter_adapter` 공용 프롬프트 빌더 + 응답 파서. 매 호출마다 few-shot 예시 숫자를 지터링해서 모델이 예시값을 그대로 베끼는 걸 방지(`_jitter_stage_params`). `parse_mood()`가 모든 범위 클램프·기본값 채움의 단일 지점(예: `target_minutes` 하한이 2026-08-11에 10→30분으로 상향 — AI 모드가 너무 짧은 플레이리스트를 만들던 버그 수정). |

### 2.4 api/ — 라우트 + DTO

`routes.py` 엔드포인트:

| 메서드/경로 | 역할 |
|---|---|
| `GET /api/health` | 상태 + 버전 + 현재 활성 interpreter 종류(stub/groq/openrouter 감지용). |
| `GET /api/bands` | 밴드 필터 UI용 밴드 목록+곡 수. |
| `GET /api/songs` | '곡 추가' 미니 브라우저용 전체 곡 목록(음차 검색 필드 포함). |
| `POST /api/setlist` | 메인 엔드포인트. custom 모드거나 레이트리밋 어댑터가 아니면 동기 처리, AI 모드+TPM 리밋 활성이면 잡을 등록하고 **202**+`job_id`/예상 대기시간/큐 위치 반환. |
| `GET /api/setlist/status/{job_id}` | 잡 폴링(큐잉/실행중/완료/에러). |
| `POST /api/admin/refresh-data` | `data` 브랜치 CSV 즉시 강제 재fetch(오토로더 전용, `DATA_REFRESH_TOKEN` 헤더 일치 시에만 opt-in 동작, 미설정이면 항상 403). |

`schemas.py`: `StageInput`(custom 모드 단계 입력), `SetlistRequest`(요청 DTO), `serialize_setlist()`(도메인 `Setlist`→응답 dict 변환).
`errors.py`: `map_error()` — 동기 예외 핸들러와 백그라운드 잡 러너가 동일한 에러 응답을 내도록 하는 공용 매핑.
`band_aliases.py`: 프롬프트 문자열에서 밴드를 자동 감지하는 별칭 사전(`detect_bands`) — "레이" 같은 오탐 별칭은 제거된 이력 있음.

### 2.5 repo/ — 데이터 로딩

| 파일 | 역할 |
|---|---|
| `song_repo.py` | `songs_master.csv`(+선택적 가사 임베딩)를 읽어 `Song` 리스트로 변환. `energy`는 acousticness/energy_full/시간대별 강도 지표를 합성한 soft-OR 조합값, 6종 오디오 피처는 밴드 후보군 기준 minmax 스케일링. |
| `remote_source.py` | `main` 브랜치에는 `data/`가 없으므로 `data` 브랜치의 CSV/JSON을 `raw.githubusercontent.com`에서 런타임에 fetch·캐시(로컬 캐시 폴백 포함). |
| `ja_transliteration.py` | 일본어 곡명 → 로마자/한글/한자음 변환(검색 전용, 원본 CSV는 건드리지 않음). pykakasi + 외래어 사전 + hanja 패키지 조합. |
| `song_alias_overrides.json` | `idx` 키로 자동 변환 오류를 수동 오버라이드(현재 비어있음, 형식은 백엔드 README 참조). |

### 2.6 main.py / jobs.py — 조립 + 큐

- `main.py`: composition root. `_build_interpreter()`가 유일한 어댑터 선택 지점, `create_app()`이
  `app.state`에 interpreter/notifier/embedder/songs/job_store를 조립. `InflightLimitMiddleware`가
  동시 요청 수를 `REQUEST_QUEUE_MAX`(기본 200)로 제한. `_lifespan()`이 데이터 주기 리프레시
  백그라운드 루프를 돈다.
- `jobs.py`: `ThreadPoolExecutor` 기반 `JobStore`. `Job.estimated_wait_seconds()`는 과거 관측된
  최솟값으로 클램프해 대기시간이 다시 늘어나 보이는 UX 버그를 막는다(2026-08-12 수정).

### 2.7 알려진 문서-코드 불일치

`.env.example`은 여전히 OpenRouter를 "필수" LLM 경로로, `MOOD_INTERPRETER`를 `stub|openrouter`로만
안내한다. 실제로는 Groq(`GROQ_API_KEY`)가 기본 경로이고 `groq_multistage`도 존재한다. 다음에
`.env.example`을 만질 일이 있으면 함께 동기화할 것.

---

## 3. 프론트엔드 (`src/frontend/`)

### 3.1 로드 순서 = 의존 순서 (classic script, 전역 공유)

```
i18n.js → utils.js → state.js → omakase.js → request-flow.js → band-filter.js →
stage-graph.js → mode-switch.js → render-result.js → camelot-wheel.js → track-menu.js →
youtube-player.js → track-edit.js → presets.js → song-picker.js →
youtube-playlist-save.js → share-modal.js → playbar.js → main.js
```

`i18n.js`·`utils.js`가 leaf(다른 파일이 참조, 자신은 무의존), `main.js`가 부트스트랩(마지막).

### 3.2 파일별 요약

| 파일 | 역할 |
|---|---|
| `i18n.js` | KO/JA/EN/zh-Hans/zh-Hant 번역 테이블. `t()`/`tArr()`/`setLang()`/`applyStaticI18n()`. 언어 전환 시 `i18n:change` 커스텀 이벤트를 쏴서 다른 모듈이 동적 텍스트를 재렌더하게 한다(자신은 다른 모듈을 모름 — 역방향 의존). |
| `utils.js` | `$`, `track`(umami 래퍼), `clamp`/`clamp01`, `show`/`hide`/`toggle`, `BAND_ORDER`/`bandsInSelectorOrder`, `makeBandIcon`, `keyLabel`, `PICK_PARAM_DEFS`(6개 오디오 지표 뱃지 정의) 등 전역 leaf 헬퍼. |
| `state.js` | 중앙 가변 상태(전역 `let`/`const`) — `picks`, `current`, `stageModel` 등 다른 모든 파일이 직접 읽고 쓰는 허브. 테마 토글, 언어 팝업 UI도 여기서 배선. |
| `omakase.js` | "오마카세" 버튼 — 시간대+날씨(Open-Meteo, 프론트에서 직접 호출) 기반 프롬프트 자동 생성. |
| `request-flow.js` | `POST /api/setlist` 제출 플로우(AI/Custom 모드), 202 응답 시 `GET /api/setlist/status/{job_id}` 폴링 큐 UX, 로딩 애니메이션. |
| `band-filter.js` | 전역 밴드 체크리스트 + 단계별 "밴드 고정" 팝업. `manualBands`(사용자가 직접 체크한 것)와 프롬프트 자동감지 밴드를 분리 추적해 요청마다 누적되지 않게 한다. |
| `stage-graph.js` | **가장 큰 파일(~700줄)**. Custom 모드/고급설정 편집기 전체: 2D valence×energy 무드맵, 시간배분 바(드래그로 단계 경계 조절), 단계별 가사 인상 텍스트+밴드고정 팝업, 5종 고급 파라미터(러프니스/LRA/댄서빌리티/악기비중/음절밀도) 스플라인 그래프. `renderStageGraph()`가 매번 전체 재구성. |
| `mode-switch.js` | AI↔Custom 모드 전환, 두 모드 간 단계 데이터 형태 변환(`prefillCustomFromLast`). |
| `render-result.js` | API 응답(또는 복원된 프리셋)을 전체 UI에 반영하는 중앙 함수 `renderResult()` — 요약/트랙리스트/카멜롯휠/설정 반영을 모두 조율. |
| `camelot-wheel.js` | 플레이리스트의 키 이동 경로를 카멜롯 휠 SVG로 시각화(하모닉 호환 여부에 따라 초록 실선/주황 점선). |
| `track-menu.js` | 트랙 롱프레스/우클릭 컨텍스트 메뉴 + 곡 파라미터 뱃지의 공용 툴팁 시스템. |
| `youtube-player.js` | YouTube IFrame Player API 래퍼 — 자동 다음곡 재생, 재생불가 곡 자동 스킵, umami 마일스톤 이벤트. |
| `track-edit.js` | 트랙리스트 포인터 드래그 재정렬, 곡 삭제, undo 스택. |
| `presets.js` | localStorage 기반 "저장된 플레이리스트"(최대 50개), 삭제 undo. |
| `song-picker.js` | "+"로 여는 곡 추가 모달 — `/api/songs` 캐시 + 로마자/한글/한자음 포함 검색. |
| `youtube-playlist-save.js` | Google OAuth(클라이언트 사이드, GIS)로 사용자의 실제 YouTube 플레이리스트에 저장. 실패 시 익명 `watch_videos` URL로 폴백. |
| `share-modal.js` | 공유 모달 — 익명 URL 복사 + 계정 저장 기능 위임. |
| `playbar.js` | 하단 고정 재생바 — 진행바, 제목 마퀴, 반복 모드, 애니메이션 웨이브 링, 트랙리스트/휠 스크롤 동기화. |
| `main.js` | 최종 부트스트랩 — 밴드 목록 로드, 단계 모델 초기화, 모드 초기 상태 적용, 첫 렌더, 버전 정보 표시. |

### 3.3 CSS (`style/*.css`, 로드 순서=캐스케이드 순서)

`base.css`(변수·리셋, 항상 첫 번째) → `form-controls.css` → `mood-map.css` → `loading-summary.css`
→ `player-tracklist.css` → `song-picker-modal.css` → `share-modal.css` → `footer-menu.css` →
`playbar.css` → `camelot-wheel.css`. 각각 이름 그대로 해당 컴포넌트만 스타일링한다.

### 3.4 정적 페이지

`index.html`(SPA 본체), `privacy.html`/`terms.html`(개인정보처리방침/이용약관, `base.css`+
`footer-menu.css`만 사용하는 독립 정적 페이지).

### 3.5 알려진 이슈

`track-menu.js:66`의 `attachTrackLongPress`가 `LONGPRESS_MS` 상수를 참조하지만 `app/` 어디에도
정의돼 있지 않다(grep 확인 완료) — 터치 기기에서 트랙을 롱프레스하면 타이머 콜백이
`ReferenceError`로 죽는 잠재 버그. 문서화만 해두고 이번 작업 범위에서는 수정하지 않았다.

---

## 4. 더 볼 것

- 원칙/계약 원본: `docs/architecture.md`
- 폴더별 작성규칙: `src/backend/README.md`, `src/frontend/README.md`
- 데이터 흐름(브랜치 분리 이유 등): 루트 `CLAUDE.md`의 "데이터 브랜치" 절
