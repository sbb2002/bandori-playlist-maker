# 코드설계팀 — 파일럿 프로토타입 구현 보고서

작성: 부장(메인 세션) · 2026-07-10 · 근거: PRD §4, architecture.md(스키마 3종 동결), 사용자 지시("설계부서만 움직여 프로토타입부터, 최종목표=앱 구동 확인")

## 목표

architecture.md 동결 설계 그대로 백엔드(FastAPI·클린 아키텍처)+정적 프론트+테스트를 구현하고, **앱이 실제로 구동됨(요청→선곡→순차재생 파이프라인)** 을 확인한다. OpenRouter 키 등 env는 미제공 상태이므로 키 없이도 끝까지 도는 구성으로 우선 구현.

## 수행 내용

architecture.md §② 디렉토리 구조·§③ 스키마 3종을 그대로 구현. 부장이 직접 구현(토큰 절약 — 설계가 완결적이라 서브에이전트 콜드스타트 비용이 불필요하다고 판단, R8).

### 백엔드 `src/backend/` (T1~T4 통합)
- `app/domain/` (순수 계층): `models.py`(Song·MoodParameters·Setlist/Pick/Stage/PickReason·NoSetlistError), `energy.py`(단계 에너지 선형보간·곡수 산정·균등분배), `harmonic.py`(camelot cross-team import 래퍼), `selection.py`(`build_setlist()` 순수·결정적 엔진).
- `app/ports/mood_port.py`: `MoodInterpreter` Protocol + `MoodInterpretationError`·`LLMUpstreamError`.
- `app/adapters/`: `prompt.py`(시스템 프롬프트·JSON 스키마·파싱/클램프/기본값), `openrouter_adapter.py`(운영 구현, httpx·주입가능 클라이언트), **`stub_adapter.py`(신규 — 아래 설계 이탈 참조)**.
- `app/repo/song_repo.py`: `data/songs_master.csv`(660곡) → list[Song] 로더. video_id는 CSV 컬럼 신뢰, 없으면 `video_id.py` cross-team로 폴백.
- `app/api/`: `schemas.py`(요청 pydantic 검증 + Setlist 직렬화), `routes.py`(POST /api/setlist·GET /api/health).
- `app/main.py`: composition root — 어댑터 주입, CORS(FRONTEND_ORIGIN + dev localhost, 와일드카드 금지), 예외 핸들러 5종(400/422/502/409/500 스키마3 매핑).
- `requirements.txt`.

### 프론트 `src/frontend/` (T5)
- `index.html`·`app.js`·`style.css` — 빌드 스텝 없는 정적 3파일. 자연어 입력창, 세부설정(분·단계), 로딩 애니메이션("플레이리스트를 만드는 중입니다~"), YouTube IFrame Player 순차 자동전환, 선곡 이유 표시, umami 이벤트 3종(`playlist_created`·`song_advance`·`playlist_half_played`) 계측. API 베이스는 `window.SETLIST_API_BASE`로 교체(GitHub Pages↔Render 분리 대비).

### 테스트 `src/tests/` (40개 전부 통과)
- `test_harmonic`·`test_energy`·`test_selection`(도메인 순수, 결정성·중복방지·필터·seed·NoSetlist), `test_openrouter_adapter`(HTTP 목킹, 성공·클램프·업스트림/파싱 에러), `test_api`(TestClient, 계약·에러코드·CORS 비와일드카드).

## 완료 목록
- [x] 클린 아키텍처 경계(도메인 순수·포트/어댑터 격리) — domain에 외부 import 없음, LLM 없이 단위테스트 가능 확인.
- [x] 스키마 3종 동결 준수(임의 변경 없음).
- [x] 선곡 엔진 결정적·순수 — 동일 요청 2회 동일 순서 확인.
- [x] **앱 구동 확인**: 실서버 기동 → 60분 요청 시 17곡/3단계(에너지 0.40→0.53→0.65 선형)/추정 60.4분, **seed 이후 전환 16/16 하모닉(same·adjacent)**. 30분 요청 시 8곡/28.4분. 에러 케이스 400/422/409 정상.
- [x] 프론트 3파일 정적 서빙 200, app.js 문법 검증 통과.
- [x] 경로 규칙(R6/R11): 변경분 전부 `src/backend|frontend|tests` 내부. `src/scripts/data/`는 읽기전용 import만.

## 미완료 / 유의 (설계 이탈 1건 + env 대기)
- **설계 이탈(승인 요청)**: architecture.md §②에 없던 `adapters/stub_adapter.py`를 추가했다. **스키마 변경이 아니라** 동일 `MoodInterpreter` 포트 뒤의 대체 어댑터(키워드 휴리스틱, 오프라인·결정적)로, "키 없이 앱 구동 확인"이라는 이번 마일스톤을 위한 것이다. `main.py`가 `OPENROUTER_API_KEY` 유무로 자동 선택(키 있으면 OpenRouter). 포트 격리 원칙에 부합하며, 운영 전환 시 stub은 그대로 두거나 삭제 가능. → 부장 판단으로 추가, **사용자 최종 확인 요청**.
- **env 미제공(대기)**: `OPENROUTER_API_KEY`·`OPENROUTER_MODEL`·`FRONTEND_ORIGIN`. 현재는 stub로 대체 구동 중. 키 제공 시 무설정으로 OpenRouter 경로 자동 활성.
- **duration 백필 미적용(architecture.md §⑥-1)**: 곡 길이 데이터 부재로 `avg_song_seconds=213` 추정치 사용 중(재생시간이 그만큼 오차). YouTube Data API 백필은 별도 티켓·키 필요.
- **CLAUDE.md `Project status` 문구 낙후**: "PRD만 있고 코드 없음"으로 남아 실제와 불일치 — 갱신은 사용자 확인 후.

## 다음 단계 제안
1. 사용자: stub 어댑터 추가 승인 여부 + OpenRouter 키/모델/FRONTEND_ORIGIN 제공.
2. 키 수령 후 OpenRouter 실경로 스모크 테스트(어댑터 격리로 코드 변경 0).
3. `/code-review` 병행 후 커밋(현재 미커밋 — 사용자 지시 대기).
4. 호스팅 플랫폼 확정 시 배포(백엔드 Render 등 + 프론트 GitHub Pages, CORS 오리진 확정).
