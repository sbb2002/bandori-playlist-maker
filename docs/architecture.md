# setlist-maker 아키텍처 설계서 (파일럿)

작성: 코드설계팀 팀장 (opus) · 2026-07-10 · 부장 검수 승인
근거: PRD §4/§8/§9, 데이터팀 인계노트 7건(docs/reports/2026-07-10-data-team-complete.md),
`songs_master.csv` 실측 스키마, `camelot.py`/`video_id.py` 인터페이스

## ① 목표

PRD 파일럿 범위(§4)를 클린 아키텍처(§8)로 구현하기 위한 (a) 경계 설계, (b) 팀 간 계약이 되는
핵심 스키마 3종, (c) 오픈 퀘스천(§9) 결정 제안, (d) 구현 티켓 분할.

핵심 불변식 (§8 필수):
1. **도메인 순수성** — 무드 스키마·선곡 규칙은 외부 서비스 무의존 순수 함수. LLM 없이 단위 테스트 가능.
2. **어댑터 격리** — LLM 호출은 포트 뒤 어댑터 1개로 격리. 모델·벤더 교체 = 어댑터 1파일 교체.

## ② 아키텍처

### 디렉토리 구조

> **[2026-07-10 R11 개정]** 모든 소스코드는 `./src/` 하위로 이동 — 아래 트리의 `backend/`·
> `frontend/`·`tests/`·`scripts/`는 각각 `src/backend/`·`src/frontend/`·`src/tests/`·
> `src/scripts/`를 뜻한다. 폴더별 작성규칙은 각 폴더의 `README.md` 참조.

```
bandori-playlist-maker/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                  # FastAPI 앱 생성, CORS, 라우터 등록, 의존성 조립(composition root)
│  │  ├─ api/
│  │  │  ├─ routes.py             # POST /api/setlist, GET /api/health
│  │  │  └─ schemas.py            # pydantic 요청/응답 DTO (스키마3)
│  │  ├─ domain/                  # ── 순수 계층: 외부 import 금지(표준 라이브러리·자기 모듈만) ──
│  │  │  ├─ models.py             # Song, MoodParameters(스키마1), Setlist/Pick(스키마2)
│  │  │  ├─ selection.py          # build_setlist(): 선곡 엔진 순수 함수 (진입점)
│  │  │  ├─ energy.py             # 단계별 에너지 목표 산출 + 곡 수 산정
│  │  │  └─ harmonic.py           # 하모닉 호환 판정 래퍼 (a==b or is_adjacent(a,b))
│  │  ├─ ports/
│  │  │  └─ mood_port.py          # MoodInterpreter 인터페이스: interpret(prompt)->MoodParameters
│  │  ├─ adapters/
│  │  │  ├─ openrouter_adapter.py # MoodInterpreter 구현 ← 벤더 교체 시 이 파일만 교체
│  │  │  └─ prompt.py             # 시스템 프롬프트 + LLM JSON 스키마 + 파싱/검증→MoodParameters
│  │  └─ repo/
│  │     └─ song_repo.py          # data/songs_master.csv 로더 → list[Song]
│  └─ requirements.txt
├─ frontend/                      # 정적 — GitHub Pages 배포 전제(빌드 스텝 없음)
│  ├─ index.html                  # 자연어 입력창 + 결과·플레이어 영역
│  ├─ app.js                      # fetch, YouTube iframe Player, 자동 전환, umami 이벤트 3종
│  └─ style.css
├─ tests/
│  ├─ test_harmonic.py / test_energy.py / test_selection.py
│  ├─ test_openrouter_adapter.py  # HTTP 목킹
│  └─ test_api.py                 # 엔드포인트 계약·CORS·에러
└─ data/, scripts/data/           # ← 데이터팀 소유(현 src/scripts/data/). 코드팀은 읽기 전용 소비만.
```

### 경계 (의존 방향 = 안쪽으로만)

`frontend` → HTTP/JSON → `api`(DTO·에러 매핑) → `domain`(순수) ← `ports`(도메인 정의 인터페이스)
← `adapters`(OpenRouter 구현) / `repo`(CSV 로더). `main.py`가 composition root로 어댑터를 포트
자리에 주입. `domain/`은 `adapters/`·`api/`·OpenRouter를 모른다. 벤더 교체 = 어댑터 1파일 +
주입 1줄. (investbot의 adapter→api 분리와 동형.)

**cross-team import**: `harmonic.py`는 `src/scripts/data/camelot.py`의 `is_adjacent()`를,
`song_repo.py`는 `video_id.py`를 읽기 전용 import (둘 다 표준 라이브러리 순수 함수 — 도메인
순수성 위반 아님). 코드팀은 `src/scripts/data/` 편집 금지(R6 검수 항목).

## ③ 핵심 스키마 3종 (팀 간 계약 — 동결)

### 스키마 1 — LLM 출력 (MoodParameters)

어댑터가 LLM 원시 JSON을 검증·클램프·기본값 주입 후 변환. **도메인은 항상 유효 값만 수신.**

```json
{
  "brightness": 0.7,
  "start_energy": 0.35,
  "end_energy": 0.85,
  "stage_count": 3,
  "target_minutes": 60,
  "interpretation_summary": "주말을 여는 밝고 점점 고조되는 약 1시간 흐름"
}
```

| 필드 | 타입/범위 | 기본값 | 검증 |
|---|---|---|---|
| `brightness` | number, -1.0(어두움)~+1.0(밝음) | 0.0 | 범위 밖 클램프 |
| `start_energy` | number, 0.0~1.0 | 0.4 | 클램프. `energy` 컬럼과 동일 축 |
| `end_energy` | number, 0.0~1.0 | start_energy | 클램프. start↔end 차이 = 진행 방향 |
| `stage_count` (N) | integer, 2~5 | 3 | 경계 클램프 |
| `target_minutes` | integer\|null, 10~180 | null→API가 60 적용 | 발화에서 추출 |
| `interpretation_summary` | string ≤120자 | "" | 설명 전용(로직 무영향) |

검증 실패: 누락 필드 기본값 주입 / 완전 파싱 불가 시 `MoodInterpretationError`(재시도 없음, §7).

### 스키마 2 — 선곡 엔진 입출력

```
build_setlist(songs: list[Song], params: MoodParameters, target_seconds: int,
              avg_song_seconds: int = 213) -> Setlist
```

`Song` 파일럿 사용분: `idx, band, song, video_id, camelot, energy(0–1), mode_score, shape,
eligible_band` (+ 향후 `duration_sec: int|None`).

출력 `Setlist`: `params`(에코) + `stages[{index, energy_target}]` + `estimated_total_seconds` +
`picks[{position, idx, video_id, band, song, camelot, energy, stage_index, reason}]`.
`reason` = `{stage_energy_target, matched_energy, harmonic: "seed"|"adjacent"|"same"|"non_harmonic",
prev_camelot, brightness_fit, text}`.

**알고리즘 (순수·결정적)**:
1. 곡풀: `eligible_band == True`만(653곡). 밴드 필터 확장 자리로 `band_filter: set|None` 인자
   예약(기본 None=ALL, §5-1b).
2. 밝기 랭킹: min-max 정규화한 `mode_score`(주 신호) + `shape` 보조 가중 → `params.brightness`와 비교.
3. 단계 에너지 목표: `start + (end - start) * i / (N-1)` 선형 보간.
4. 곡 수 산정: `round(target_seconds / effective_song_seconds)` 단계 균등 분배.
   `duration_sec` 있으면 실측 누적, 없으면 `avg_song_seconds` 추정.
5. 단계 내 선곡: 에너지 근접 후보 중 직전 곡과 하모닉 호환(`a==b or is_adjacent(a,b)`) 우선.
   첫 곡(seed)은 하모닉 제약 없음. 인접 고갈 시 non_harmonic 폴백(하드 필터 아님 — key 신뢰도
   미검증 감안).
6. 중복 방지: `idx` unique. 같은 밴드 연속 억제는 동점 타이브레이크로만.

### 스키마 3 — 백엔드 API

```
POST /api/setlist   { "prompt": str, "target_minutes"?: int|null, "stage_count"?: int }
  → 200: Setlist 객체 그대로
GET /api/health     → 200 { "status": "ok" }
```

**CORS**: `FRONTEND_ORIGIN` 환경변수(GitHub Pages 오리진)만 명시 허용 + 개발용 localhost.
와일드카드 금지.

**에러** (공통 `{ "error": { "code", "message" } }`, 재시도 없음):
| 상황 | HTTP | code |
|---|---|---|
| 잘못된 요청 | 400 | INVALID_REQUEST |
| LLM 파싱 불가 | 422 | MOOD_UNINTERPRETABLE |
| OpenRouter 실패/레이트리밋 | 502 | LLM_UPSTREAM_FAILED |
| 세트리스트 구성 불가 | 409 | NO_SETLIST |
| 기타 | 500 | INTERNAL |

프론트: 요청 중 "플레이리스트를 만드는 중입니다~" 애니메이션(§9 콜드스타트 UX).

## ④ 오픈 퀘스천 결정 (부장 잠정 승인 — 사용자 최종 결재 대기)

1. **에너지 단계 N: 기본 3, 범위 2~5.** 60분≈17곡 기준 N=3이면 단계당 5~6곡으로 지각 가능한
   아크. N 6+는 단계당 곡 수 부족으로 하모닉 후보 고갈.
2. **곡 길이 데이터 부재** (master CSV에 duration 없음 — 실측 확인):
   - **1순위**: 데이터팀이 YouTube Data API `videos.list?part=contentDetails`로 `duration_sec`
     1회 백필 (660곡 ≈ 14콜, 무료 쿼터 내, OAuth 불필요 — **API 키는 필요, 사용자 발급 요청**).
   - 대체: `avg_song_seconds=213` 플레이스홀더(오차가 재생시간에 그대로 반영).
   - 공통: 프론트 `getDuration()`으로 실제 경과 추적 → `playlist_half_played` 판정.
     엔진 사이징은 iframe에 의존 불가(재생 전 미확보).
3. **OpenRouter 모델**: 경량 구조화 추출(입 ~300/출 ~150토큰)이라 저가 소형 모델 1차
   (Haiku/Gemini Flash/mini 계열), 요청당 ~$0.001 수준. 정확한 모델 ID·단가는 구현 직전 검증
   (어댑터 격리로 지연 무비용).
4. **선곡 이유 노출: YES.** reason 메타는 엔진이 LLM 비용 0으로 생성. API 항상 포함, 프론트가
   표시 강도 조절(접이식/보조 텍스트).

## ⑤ 구현 티켓 (T1 선행 → {T2, T3, T5} 병렬 → T4)

| 티켓 | 목표 | 산출물 | 모델(§1.5) | 의존 |
|---|---|---|---|---|
| T1 | 도메인 모델 + CSV 로더 | domain/models.py, repo/song_repo.py, tests | **haiku** | 선행 단독 |
| T2 | 선곡 엔진 순수 함수 | domain/selection.py·energy.py·harmonic.py, tests 3종 | **sonnet** (②③) | T1 후. T3·T5와 병렬 |
| T3 | LLM 포트 + OpenRouter 어댑터 | ports/mood_port.py, adapters/, test(목킹) | **sonnet** (①③) | T1 후. T2·T5와 병렬 |
| T4 | FastAPI 조립·CORS·에러 | main.py, api/, requirements.txt, test_api.py | **sonnet** (②) | T2·T3 후 |
| T5 | 정적 프론트 + iframe + umami | frontend/ 3파일 | **haiku** (반려 2회 시 상향) | 스키마3 동결로 즉시. 통합 검증만 T4 후 |

검증 기준 상세는 각 티켓 스폰 프롬프트에 팀장 명세 원문 반영할 것.

## ⑥ 미해결 (상위 결재·타팀 협조)

1. `duration_sec` 백필 승인 + YouTube Data API 키 발급 (사용자) — T2를 차단하지는 않음(양쪽 수용 설계).
2. ④ 제안값(N=3, 이유 노출 등) 사용자 최종 결재.
3. `FRONTEND_ORIGIN` 확정 — GitHub Pages 프로젝트 페이지 기준 `https://sbb2002.github.io` 예상.
4. key 신뢰도 미검증 — non_harmonic 표기로 완화, 실사용 피드백으로 재평가.
5. 백엔드 호스팅 플랫폼(§9) — 아키텍처는 플랫폼 무관, 배포 시점 결정.
