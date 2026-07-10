"""포트(도메인이 정의하는 인터페이스) 계층.

LLM 호출은 `MoodInterpreter` 포트 뒤로 격리한다. 벤더 교체 = 어댑터 1파일 교체
(architecture.md §① 불변식 2).
"""
