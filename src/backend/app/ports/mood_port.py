"""MoodInterpreter 포트 — 자연어 발화 → MoodParameters 인터페이스.

도메인·API는 이 인터페이스만 알며 OpenRouter 등 구현 세부를 모른다.
`typing.Protocol`을 쓰므로 어댑터는 상속 없이 구조적 준수만으로 포트를 만족한다.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.models import MoodParameters


class MoodInterpretationError(Exception):
    """LLM 응답을 MoodParameters로 파싱·검증할 수 없음. API에서 422 MOOD_UNINTERPRETABLE."""


class LLMUpstreamError(Exception):
    """LLM 업스트림 호출 실패(네트워크·HTTP 오류). API에서 502 LLM_UPSTREAM_FAILED."""


class LLMRateLimitError(LLMUpstreamError):
    """LLM 레이트리밋(429)이 재시도 소진 후에도 지속. API에서 429 RATE_LIMITED로 매핑.

    LLMUpstreamError 하위라 전용 핸들러가 없어도 502로 폴백되지만, main.py가 전용 429
    핸들러를 등록해 '지금 요청이 많아요' 안내로 매핑한다(트래픽 급증 대비)."""


class MoodInterpreter(Protocol):
    """무드 해석 포트. 구현은 `adapters/` 하위 단일 파일(벤더별)."""

    def interpret(self, prompt: str) -> MoodParameters:
        """자연어 발화를 검증된 MoodParameters로 변환한다.

        Raises:
            MoodInterpretationError: 응답을 해석할 수 없는 경우(재시도 없음, PRD §7).
            LLMUpstreamError: 업스트림 호출 자체가 실패한 경우.
        """
        ...
