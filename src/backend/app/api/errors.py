"""도메인/LLM 예외 → HTTP 에러 응답(스키마3) 매핑.

main.py의 동기 예외 핸들러와 jobs.py의 백그라운드 잡 러너(요청 컨텍스트 밖이라 FastAPI
예외 핸들러가 못 잡음) 양쪽이 이 매핑 하나를 공유해, 같은 예외가 어느 경로로 와도 같은
status_code·code·message로 귀결되게 한다.
"""

from __future__ import annotations

from fastapi import HTTPException

from ..domain.models import NoSetlistError
from ..ports.mood_port import LLMRateLimitError, LLMUpstreamError, MoodInterpretationError


class QueueFullError(Exception):
    """jobs.JobStore가 정원(max_queue_len) 초과로 새 잡 등록을 거절함. API에서 429 QUEUE_FULL.

    여기(도메인 예외들과 같은 자리)에 두는 이유: jobs.py가 이미 이 모듈의 map_error()를
    가져다 쓰는데, 반대 방향(errors.py → jobs.py)으로 import하면 순환참조가 된다.
    """


def map_error(exc: Exception) -> tuple[int, str, str]:
    """예외 → (status_code, error_code, message). 알려지지 않은 예외는 500 INTERNAL."""
    if isinstance(exc, HTTPException):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            err = exc.detail["error"]
            return exc.status_code, err.get("code", "HTTP_ERROR"), err.get("message", "요청에 오류가 있습니다.")
        return exc.status_code, "HTTP_ERROR", str(exc.detail) if exc.detail else "요청에 오류가 있습니다."
    if isinstance(exc, MoodInterpretationError):
        return 422, "MOOD_UNINTERPRETABLE", "요청을 무드로 해석하지 못했습니다."
    # LLMRateLimitError가 LLMUpstreamError 하위라 먼저 검사해야 한다(안 그러면 502로 잘못 매핑).
    if isinstance(exc, LLMRateLimitError):
        return 429, "RATE_LIMITED", "지금 요청이 많아요. 잠시 후 다시 시도해 주세요. 🙏"
    if isinstance(exc, LLMUpstreamError):
        return 502, "LLM_UPSTREAM_FAILED", "LLM 호출에 실패했습니다. 잠시 후 다시 시도하세요."
    if isinstance(exc, NoSetlistError):
        return 409, "NO_SETLIST", "조건에 맞는 세트리스트를 만들 수 없습니다."
    if isinstance(exc, QueueFullError):
        return 429, "QUEUE_FULL", "지금 대기열이 가득 찼어요. 잠시 후 다시 시도해 주세요. 🙏"
    return 500, "INTERNAL", "서버 내부 오류가 발생했습니다."
