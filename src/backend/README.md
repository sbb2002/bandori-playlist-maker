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
