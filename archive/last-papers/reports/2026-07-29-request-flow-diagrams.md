# 2026-07-29 — 백엔드 실행 흐름 다이어그램 (기동 / 백그라운드 / 요청 / 이벤트)

> **상태: 코드 리딩 기록.** 세션에서 `src/backend/app/main.py`·`api/routes.py`·
> `repo/remote_source.py`·`repo/song_repo.py`·`adapters/groq_adapter.py`·
> `adapters/telegram_notifier.py`·`domain/selection.py`를 근거로 정리했다. 구현이 아니라
> **현재 동작을 트리거(언제 실행되는가) 기준 4분류로 도식화**한 문서다 — 다음에 이 경로를
> 수정할 때 참조용.

## 분류 기준

"처음 시작 시 / 사용자 요청 시" 2분류로는 주기적 백그라운드 리프레시와 에러·관리자 트리거가
빠진다. 실행 빈도로 보면 4가지:

| 구분 | 시점 | 빈도 | 코드 진입점 |
|---|---|---|---|
| 1. 기동 시 | 프로세스 시작 | 1회 | `main.py:323 create_app()` |
| 2. 백그라운드 주기 | 기동 후 지속 | 반복(기본 30분) | `main.py:302 _refresh_loop()` |
| 3. 사용자 요청 시 | HTTP 요청 | 요청마다 | `api/routes.py` 각 핸들러 |
| 4. 조건부/이벤트 트리거 | 특정 이벤트 | 비정기 | `main.py:214 _alert()`, `api/routes.py:194 refresh_data()` |

미들웨어 실행 순서 주의: `main.py:328-335`에서 `InflightLimitMiddleware`를 먼저
`add_middleware`하고 `CORSMiddleware`를 나중에 추가하므로, **실행 시에는 CORS가 가장
바깥, Inflight가 그 안쪽**이다(나중에 추가한 미들웨어가 바깥을 감싸는 Starlette 규칙 —
503 거절 응답에도 CORS 헤더가 붙게 하려는 의도, `main.py:233` 주석).

---

## 1. 서버 기동 시 (`create_app()`, 1회)

```mermaid
flowchart TD
    A["프로세스 시작"] --> B["_load_dotenv()<br/>.env → os.environ"]
    B --> C["FastAPI(lifespan=_lifespan) 생성"]
    C --> D["add_middleware(Inflight)<br/>add_middleware(CORS)<br/>(CORS가 바깥)"]
    D --> E["app.state.version = _compute_version()"]
    E --> F["app.state.interpreter = _build_interpreter()<br/>Groq / GroqMultistage / Stub 중 택1<br/>(인스턴스 생성만, API 호출 없음)"]
    F --> G["app.state.notifier = _build_notifier()<br/>Telegram or Noop"]
    G --> H["app.state.songs = _load_current_songs()"]
    H --> H1["remote_source.ensure_songs_csv()<br/>data 브랜치 raw.githubusercontent.com<br/>최초 HTTP GET (캐시 없을 때만)"]
    H1 --> H2["song_repo.load_songs(path)<br/>CSV 파싱 → Song 리스트<br/>(로마자/한글/한자음 캐시 계산)"]
    H2 --> I["app.include_router(router)<br/>_register_exception_handlers(app)"]
    I --> J["uvicorn: lifespan 진입<br/>(2번 백그라운드 루프 시작) → 요청 서빙 개시"]
```

---

## 2. 백그라운드 주기 루프 (`_refresh_loop`, 요청과 무관)

```mermaid
flowchart TD
    S(["lifespan 시작"]) --> L{"DATA_REFRESH_INTERVAL_SEC > 0?"}
    L -- "아니오(0)" --> N["루프 비활성 — 기동 시 1회 로드만 유지"]
    L -- "예(기본 1800s)" --> W["asyncio.sleep(interval)"]
    W --> F["asyncio.to_thread(_load_current_songs, force=True)"]
    F --> F1["remote_source.ensure_songs_csv(force=True)<br/>강제 재fetch"]
    F1 --> F2["song_repo.load_songs"]
    F2 --> OK{"성공?"}
    OK -- "예" --> R["app.state.songs 교체<br/>(다음 요청부터 새 데이터)"]
    OK -- "아니오" --> K["로그만 남기고 유지<br/>(기존 app.state.songs 그대로)"]
    R --> W
    K --> W
```

---

## 3. 사용자 요청 시

### 3a. 읽기전용 GET — `/api/health`, `/api/bands`, `/api/songs`

```mermaid
sequenceDiagram
    participant C as 클라이언트
    participant CORS as CORSMiddleware
    participant IF as InflightLimitMiddleware
    participant R as routes.py 핸들러
    participant S as app.state

    C->>CORS: GET /api/health 등
    CORS->>IF: 통과
    IF->>R: prefix가 /api/setlist 아님 → 카운트 안 건드리고 통과
    R->>S: 캐시된 값만 읽음(interpreter_name, songs, ...)
    R-->>C: dict → CORS 헤더 부착 → 응답
```
외부 호출·LLM·Inflight 카운트 제한 모두 없음 — 가장 가벼운 경로.

### 3b. `POST /api/setlist` (핵심 경로)

```mermaid
sequenceDiagram
    participant C as 클라이언트
    participant CORS as CORSMiddleware
    participant IF as InflightLimitMiddleware
    participant R as create_setlist()
    participant Groq as GroqMoodInterpreter(어댑터)
    participant Ext as Groq API(외부)
    participant Dom as build_setlist(순수함수)

    C->>CORS: POST /api/setlist {prompt, ...}
    CORS->>IF: 통과
    IF->>IF: count += 1 (limit 초과 시 즉시 503 반환, 4번 참조)
    IF->>R: 통과
    R->>R: Cache-Control: no-store<br/>band_names = payload.bands ∪ detect_bands(prompt)<br/>energy_stats 계산
    R->>Groq: interpreter.interpret(prompt, previous_prompt, energy_stats)
    Groq->>Ext: Chat Completions API POST
    alt 429/5xx
        Ext-->>Groq: 오류
        Groq->>Ext: GROQ_MAX_RETRIES만큼 백오프 재시도
    end
    alt 200이지만 무드 JSON 파싱 실패
        Groq->>Ext: GROQ_MOOD_RETRIES만큼 재호출
    end
    Ext-->>Groq: 200 + 무드 JSON
    Groq-->>R: MoodParameters
    Note over R: 실패 시 LLMRateLimitError /<br/>LLMUpstreamError / MoodInterpretationError<br/>throw → main.py 예외핸들러로 전파(4번 참조)
    R->>R: honor 판정 → song_type 필터 → stage_specs 결정
    R->>Dom: build_setlist(songs, params, target_seconds, band_filter, stage_specs)
    Dom-->>R: Setlist(외부호출 없음, 실패 시 NoSetlistError)
    R->>R: serialize_setlist() + applied_bands/include_original/<br/>include_cover/honored_overrides 메타 추가
    R-->>IF: dict 반환
    IF->>IF: count -= 1 (finally)
    IF-->>CORS: 통과
    CORS-->>C: 200 JSON (헤더 부착)
```

---

## 4. 조건부 / 이벤트 트리거

### 4a. Inflight 큐 초과 — FastAPI를 거치지 않는 ASGI 레벨 응답

```mermaid
flowchart TD
    A["/api/setlist 요청 도착"] --> B{"count >= limit?<br/>(REQUEST_QUEUE_MAX, 기본 200)"}
    B -- "아니오" --> C["count += 1 → FastAPI 라우팅으로 통과"]
    B -- "예" --> D["_alert_overload()<br/>Telegram 알림 fire-and-forget 예약"]
    D --> E["_reject()<br/>raw ASGI send로 503 JSON 직접 전송<br/>(FastAPI 핸들러 자체를 거치지 않음)"]
```

### 4b. 에러 발생 시 알림 (`_alert`, 3b의 예외 경로와 연결)

```mermaid
flowchart TD
    A["도메인/어댑터에서 예외 throw"] --> B["main.py 예외 핸들러가<br/>코드별 매핑(429/502/422/409/500)"]
    B --> C{"500(INTERNAL) 또는<br/>502(LLM_UPSTREAM)?"}
    C -- "예" --> D["_alert(request, title, exc)<br/>asyncio.create_task(notifier.notify(...))<br/>— await 안 함, fire-and-forget"]
    D --> E["TelegramNotifier.notify()<br/>같은 title 5분 스로틀 → 초과 시 무시<br/>실패해도 예외 삼킴(요청 응답에 영향 없음)"]
    C -- "아니오" --> F["알림 없이 바로 JSONResponse 반환"]
    B --> G["JSONResponse 반환<br/>(알림 여부와 무관하게 클라이언트에는 항상 응답)"]
```

### 4c. 관리자 강제 리프레시 — `POST /api/admin/refresh-data`

```mermaid
flowchart TD
    A["오토로더(외부)가 data 브랜치 push 직후 호출"] --> B["X-Refresh-Token 헤더를<br/>DATA_REFRESH_TOKEN env와<br/>secrets.compare_digest 비교"]
    B -- "불일치/env 미설정" --> C["403"]
    B -- "일치" --> D["app.state.refresh_songs(force=True)<br/>(= _load_current_songs, 2번과 동일 로직 재사용)"]
    D --> E["remote_source.ensure_songs_csv(force=True)"]
    E --> F["song_repo.load_songs"]
    F --> G["app.state.songs 교체"]
    G --> H["{status: ok, song_count: n} 반환"]
```
2번(백그라운드 주기 루프)과 내부 로직은 동일하지만, 트리거가 타이머가 아니라 **오토로더의
즉시 HTTP 호출**이라는 점이 다르다 — push 직후 최대 30분(`DATA_REFRESH_INTERVAL_SEC`)을
기다리지 않게 하려는 용도(`main.py:19-20` 주석).

---

## 관련

- 근거 대화: 2026-07-29 세션(main.py 코드 리딩 중 "요청이 어떻게 흐르는지" 질문에서 파생).
- 코드 위치: `src/backend/app/main.py`, `src/backend/app/api/routes.py`,
  `src/backend/app/repo/remote_source.py`, `src/backend/app/repo/song_repo.py`,
  `src/backend/app/adapters/groq_adapter.py`, `src/backend/app/adapters/telegram_notifier.py`,
  `src/backend/app/domain/selection.py`.
- 관련 기존 문서: `archive/last-papers/reports/2026-07-15-remote-data-serving-design.md`
  (원격 데이터 서빙 설계 — 위 2번·4c 다이어그램이 구현된 결과).
