# src/tests/ — 코드설계팀 소유 (백엔드 테스트)

## 작성규칙

1. 파일 구성은 architecture.md 디렉토리 구조를 따른다: `test_harmonic.py` / `test_energy.py` /
   `test_selection.py` / `test_openrouter_adapter.py` / `test_api.py`.
2. **도메인 테스트는 LLM·네트워크 호출 금지** — 순수 함수를 구조화된 입력으로 직접 검증한다.
3. 어댑터 테스트는 HTTP를 **목킹**한다 (실제 OpenRouter 호출 금지 — 비용·비결정성).
4. 선곡 엔진은 결정적(deterministic)이어야 하므로, 동일 입력 → 동일 출력을 검증하는 테스트를
   포함한다.
5. 테스트 실패 상태를 "완료"로 보고하는 것 금지 (R3). 실패는 실패로 보고한다.
