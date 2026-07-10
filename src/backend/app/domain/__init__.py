"""도메인(순수) 계층.

외부 서비스 무의존: 표준 라이브러리 + 자기 모듈 + 허용된 cross-team import
(`src/scripts/data/camelot.py`의 하모닉 함수)만 사용한다. LLM 없이 단위 테스트 가능.
"""
