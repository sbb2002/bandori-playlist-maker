# src/backend/ — 코드설계팀 소유 (FastAPI 백엔드)

구조·스키마의 원본은 **`docs/architecture.md` (동결됨, 파일럿 설계 시점 기준)** — 이 README는
현재 코드 기준 요약이며, 원칙(불변식) 충돌 시 architecture.md가 우선한다. 파일별 상세 역할·함수
목록은 **`docs/CODEBASE_MAP.md`** 참조.

## 작성규칙 (클린 아키텍처 불변식 — 위반 시 검수 반려)

1. **`app/domain/`은 순수 계층**: 표준 라이브러리와 자기 모듈만 import. `adapters/`·`api/`·
   pydantic·HTTP 클라이언트 import 금지. 모든 함수는 LLM 없이 단위 테스트 가능해야 한다.
2. **LLM은 포트 뒤로**: 도메인·API는 `ports/mood_port.py`(`MoodInterpreter` Protocol)만 알며,
   실제 구현은 `adapters/`에 벤더별로 1파일씩 분리(`groq_adapter.py`가 현재 기본 프로덕션
   어댑터, `groq_multistage_adapter.py`는 실험적 대안, `openrouter_adapter.py`는 예비 대안,
   `stub_adapter.py`는 키 미설정 시 오프라인 폴백). 벤더 교체/전환은 `main.py`의
   `_build_interpreter()` 분기 + 해당 어댑터 파일만 건드리면 된다.
3. **의존 방향은 안쪽으로만**: `api → domain ← ports ← adapters/repo`. `main.py`가
   composition root로 조립한다(어댑터↔포트 바인딩이 일어나는 유일한 곳).
4. **스키마 3종은 팀 간 계약**(MoodParameters / Setlist / API DTO) — 임의 변경 금지. 변경이
   필요하면 부장 승인 + architecture.md 개정이 선행되어야 한다.
5. cross-team import 허용 범위: `src/scripts/data/camelot.py`의 `is_adjacent()`,
   `src/scripts/data/video_id.py` — 읽기 전용 import만, 해당 파일 편집 금지.
6. 테스트는 `src/tests/`에 작성한다 (이 폴더 안에 두지 않는다).
7. CORS는 `FRONTEND_ORIGIN` 환경변수 명시 허용만 — 와일드카드 금지. 시크릿(.env) 커밋 금지.

## LLM 어댑터 현황 (2026-08 기준)

`app/adapters/`에 무드 해석기(`MoodInterpreter`) 구현이 4개 공존한다. `main.py`의
`_build_interpreter()`가 아래 순서로 선택한다:

| 선택 조건 | 어댑터 | 특징 |
|---|---|---|
| `MOOD_INTERPRETER=groq_multistage` | `groq_multistage_adapter.py` | 실험적. LLM 호출 4회 분할(분량→단계별 무드→단계별 에너지→요약문), JSON 파싱 없이 숫자/텍스트만 받음. TPM 레이트리밋·6종 오디오 피처(`stage_params`)·다국어 미지원 — `main`에 배선돼 있지만 아직 기본 경로 아님([[decision-enable-groq-multistage-pending-review]] 참조) |
| `GROQ_API_KEY` 설정(기본) | `groq_adapter.py` | **현재 프로덕션 기본.** 단일 호출 + `adapters/prompt.py` 공용 프롬프트/파서, `rate_limiter.py`의 TPM 토큰버킷으로 사전 acquire |
| (openrouter는 코드상 남아있으나 `_build_interpreter()`가 현재 분기하지 않음) | `openrouter_adapter.py` | 예비/레거시 대안 어댑터. `.env.example`은 아직 이 어댑터를 "필수" 경로로 문서화하고 있어 실제 코드와 어긋나 있음 — 어댑터 전환 작업 시 `.env.example` 동기화 필요 |
| 키 없음 | `stub_adapter.py` | 키워드 휴리스틱, LLM 없이 오프라인 동작. 응답 요약문 끝에 `"(이 문구는 stub입니다.)"`가 붙어 `/api/health`의 `interpreter` 필드와 함께 운영 중 stub 오폴백 감지에 쓰인다 |

무드 해석 후 `app/jobs.py`의 `JobStore`(스레드풀 기반 인메모리 잡 큐)가 TPM 대기시간을 HTTP
요청 밖으로 빼서, `POST /api/setlist`는 AI 모드일 때 보통 즉시 202 + `job_id`를 반환하고
프론트가 `GET /api/setlist/status/{job_id}`를 폴링한다(custom 모드나 레이트리밋 비활성 어댑터는
동기 처리).

## 곡 제목 검색 보조 필드(로마자·한글·한자음)

### 자동 음차 변환
곡 제목이 다음과 같이 자동 변환되어 검색 보조 필드(`song_romaji`, `song_hangul`, `song_hanja_reading`)로 제공된다:

- **로마자(`song_romaji`)**: pykakasi로 칸지→히라가나→헵번식 로마자 변환
- **한글(`song_hangul`)**: pykakasi의 히라가나 단계에서 규칙기반 한글 음차 (외래어 사전 적용)
- **한자음(`song_hanja_reading`)**: hanja 라이브러리로 한자→한국 한자음(음독) 변환

'곡 추가' 미니 브라우저에서 사용자가 이 필드들로도 검색 가능하다.

### 외래어 사전 (최장일치 우선)
가타카나 외래어는 글자 단위 음차 대신 관용 한글 표기로 검색되도록 `app/repo/ja_transliteration.py`의
`_LOANWORD_HANGUL` 사전에 정의되어 있다. 예:
- ライブ(라이브/live)
- スマイル(스마일/smile)
- テレパシー(텔레파시/telepathy)

### 수동 오버라이드 (mygo 등 독자적 읽기용)
자동 변환이 틀리는 곡(특히 mygo처럼 밴드 고유의 읽기 방식)은 `app/repo/song_alias_overrides.json`에
수동으로 지정할 수 있다.

```json
{
  "277": {
    "song_hangul": "정확한 한글 표기",
    "song_romaji": "선택적 로마자",
    "song_hanja_reading": "선택적 한자음"
  }
}
```

키는 `songs_master.csv`의 `idx` 컬럼 값(문자열)이다 — 이 CSV엔 `tag` 컬럼이 없으므로 곡을
유일하게 식별하는 `idx`를 쓴다(예: mygo의 곡이 `idx=277`이면 위처럼 `"277"`). 부분 오버라이드
가능(지정된 필드만 대체, 나머지는 자동값 유지).

## 데이터 로딩

`main` 브랜치에는 `data/`가 없다 — 배포된 백엔드는 `app/repo/remote_source.py`를 통해 `data`
브랜치의 `songs_master.csv`(+선택적 `lyric_impressions.json`)를 기동 시 1회, 이후
`DATA_REFRESH_INTERVAL_SEC`(기본 1800초) 주기로 원격 재fetch한다. 로컬 개발/테스트는 `SONGS_CSV`
환경변수로 원격 fetch를 건너뛸 수 있다. 자세한 배경은 루트 `CLAUDE.md`의 "데이터 브랜치" 절 참조.
