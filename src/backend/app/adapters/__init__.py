"""어댑터 계층 — 포트의 벤더별 구현.

`openrouter_adapter.py`  : MoodInterpreter의 OpenRouter 구현(운영).
`stub_adapter.py`        : LLM 없이 도는 결정적 휴리스틱 구현(키 없이 앱 구동 검증용).
벤더 교체 = 이 폴더 내 어댑터 1파일 + `main.py` 주입 1줄(architecture.md §① 불변식 2).
"""
