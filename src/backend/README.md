# src/backend/ — 코드설계팀 소유 (FastAPI 백엔드)

구조·스키마의 원본은 **`docs/architecture.md` (동결됨)** — 이 README는 요약일 뿐이며 충돌 시
architecture.md가 우선한다.

## 작성규칙 (클린 아키텍처 불변식 — 위반 시 검수 반려)

1. **`app/domain/`은 순수 계층**: 표준 라이브러리와 자기 모듈만 import. `adapters/`·`api/`·
   pydantic·HTTP 클라이언트 import 금지. 모든 함수는 LLM 없이 단위 테스트 가능해야 한다.
2. **LLM은 포트 뒤로**: 도메인·API는 `ports/mood_port.py` 인터페이스만 알며, OpenRouter 구현은
   `adapters/openrouter_adapter.py` 단일 파일. 벤더 교체 = 어댑터 1파일 + `main.py` 주입 1줄.
3. **의존 방향은 안쪽으로만**: `api → domain ← ports ← adapters/repo`. `main.py`가
   composition root로 조립한다.
4. **스키마 3종은 팀 간 계약**(MoodParameters / Setlist / API DTO) — 임의 변경 금지. 변경이
   필요하면 부장 승인 + architecture.md 개정이 선행되어야 한다.
5. cross-team import 허용 범위: `src/scripts/data/camelot.py`의 `is_adjacent()`,
   `src/scripts/data/video_id.py` — 읽기 전용 import만, 해당 파일 편집 금지.
6. 테스트는 `src/tests/`에 작성한다 (이 폴더 안에 두지 않는다).
7. CORS는 `FRONTEND_ORIGIN` 환경변수 명시 허용만 — 와일드카드 금지. 시크릿(.env) 커밋 금지.

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
  "mygo__003": {
    "song_hangul": "정확한 한글 표기",
    "song_romaji": "선택적 로마자",
    "song_hanja_reading": "선택적 한자음"
  }
}
```

키는 CSV의 `tag` 컬럼 값이며, 부분 오버라이드 가능 (지정된 필드만 대체, 나머지는 자동값 유지).
