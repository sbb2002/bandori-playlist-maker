"""Groq 어댑터 — MoodInterpreter 포트의 운영 구현.

벤더/모델 교체 시 이 파일(과 main.py 주입 1줄)만 교체하면 된다. HTTP 세부는 여기에만 존재하며
도메인·API는 이 모듈을 모른다. 파싱/검증은 `prompt.py`에 위임한다.
"""

from __future__ import annotations

import random
import time

import httpx

from ..domain.models import MoodParameters
from ..ports.mood_port import (
    LLMRateLimitError,
    LLMUpstreamError,
    MoodInterpretationError,
)
from . import prompt as prompt_mod
from .rate_limiter import TokenBucketLimiter

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
# 파일럿 기본: 무료 경량 모델(사용자 결정 — §④-3/§9 모델 오픈퀘스천 확정). env로 교체 가능.
# 참고: reasoning 모델이라 응답이 다소 느릴 수 있으나 추출 정확도·비용(무료) 양호.
DEFAULT_MODEL = "llama-3.1-8b-instant"
DEFAULT_TIMEOUT = 60.0  # 무료/reasoning 모델 지연 감안


class GroqMoodInterpreter:
    """Groq chat/completions로 무드를 해석하는 MoodInterpreter 구현."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        referer: str | None = None,
        title: str = "setlist-maker",
        response_format_mode: str = "none",
        max_retries: int = 2,
        retry_base: float = 0.5,
        mood_parse_retries: int = 3,
        rate_per_min: float = 0.0,
        rate_max_wait: float = 20.0,
        rate_max_waiters: int = 100,
    ) -> None:
        if not api_key:
            raise ValueError("Groq api_key가 비어 있습니다.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # 주입 가능한 클라이언트(테스트 목킹용). 없으면 자체 생성.
        self._client = client or httpx.Client(timeout=timeout)
        self._referer = referer
        self._title = title
        # 트래픽 급증 대비 2단: (1) 프로액티브 레이트리밋(RPM 준수 페이싱, rate_per_min>0 시),
        # (2) 429/5xx 지수 백오프 재시도(사후 backstop). 세마포어 선블로킹은 스레드풀 고갈
        # 위험이 있어 쓰지 않고, 리미터는 대기 상한(max_wait)·대기열 상한(max_waiters)으로 보호.
        self._max_retries = max(0, max_retries)
        self._retry_base = max(0.0, retry_base)
        # 절대시간·다단계 마커가 많이 섞인 디테일한 요청은 200 응답이면서도 content가 JSON으로
        # 파싱 안 되는 경우가 간헐적으로 있다(모델이 장문 설명을 섞어 내보내는 등) — 이건 HTTP
        # 재시도(_post_with_retry, 429/5xx 대상)로는 안 잡히므로 별도로 재호출한다. 그래도 전부
        # 실패하면 기존과 동일하게 MoodInterpretationError를 올려 422 폴백 처리한다(동작 유지).
        self._mood_parse_retries = max(0, mood_parse_retries)
        self._limiter = (
            TokenBucketLimiter(rate_per_min, max_wait=rate_max_wait, max_waiters=rate_max_waiters)
            if rate_per_min and rate_per_min > 0
            else None
        )
        # 응답 포맷 강제 모드: "none"(전 모델 호환, 프롬프트+관용 파서에 의존) |
        # "json_object"(JSON 모드) | "json_schema"(structured output — 지원 모델만).
        self._response_format_mode = response_format_mode.strip().lower()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            # "X-Title": self._title,
        }
        # Groq 랭킹/식별용(선택). GitHub Pages 오리진 등.
        if self._referer:
            headers["HTTP-Referer"] = self._referer
        return headers

    def interpret(self, prompt: str, previous_prompt: str | None = None) -> MoodParameters:
        # print("TEST:", self._model, self._base_url, self._response_format_mode)
        payload = {
            "model": self._model,
            "messages": prompt_mod.build_messages(prompt, previous_prompt),
            "temperature": 0.2,
        }
        if self._response_format_mode == "json_schema":
            payload["response_format"] = prompt_mod.RESPONSE_JSON_SCHEMA
        elif self._response_format_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        # "none": response_format 미전송 — 강한 시스템 프롬프트 + 관용 파서로 처리(전 모델 호환).

        # 프로액티브 레이트리밋(RPM 준수). 대기열/대기시간 초과 시 429로 즉시 안내.
        if self._limiter is not None and not self._limiter.acquire():
            raise LLMRateLimitError("요청이 많아 대기열이 가득 찼습니다(레이트리밋).")

        last_error: MoodInterpretationError | None = None
        for attempt in range(self._mood_parse_retries + 1):
            response = self._post_with_retry(payload)

            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                last_error = MoodInterpretationError(f"Groq 응답 구조 예상 밖: {exc}")
                continue

            if not isinstance(content, str) or not content.strip():
                last_error = MoodInterpretationError("Groq 응답 content가 비어 있습니다.")
                continue

            try:
                return prompt_mod.parse_mood(content)
            except MoodInterpretationError as exc:
                last_error = exc
                continue

        # mood_parse_retries회 재시도 후에도 전부 실패 — 기존과 동일하게 폴백(422 처리는 main.py가 담당).
        assert last_error is not None
        raise last_error

    def _post_with_retry(self, payload: dict) -> httpx.Response:
        """chat/completions POST. 429/5xx는 백오프 재시도, 지속 시 적절한 예외로 매핑.

        Raises:
            LLMRateLimitError: 재시도 소진 후에도 429(레이트리밋)인 경우 → API 429.
            LLMUpstreamError:  네트워크 오류·기타 비정상 응답 → API 502.
        """
        url = f"{self._base_url}/chat/completions"
        # print("TEST:", url, payload)
        headers = self._headers()
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(url, headers=headers, json=payload, timeout=self._timeout)
            except httpx.HTTPError as exc:
                if attempt < self._max_retries:
                    time.sleep(self._backoff(attempt))
                    continue
                raise LLMUpstreamError(f"Groq 요청 실패: {exc}") from exc

            if response.status_code == 200:
                return response

            retryable = response.status_code == 429 or 500 <= response.status_code < 600
            if retryable and attempt < self._max_retries:
                time.sleep(self._retry_delay(response, attempt))
                continue

            body = response.text[:200]
            # print("TEST:", body)
            if response.status_code == 429:
                raise LLMRateLimitError(f"Groq 레이트리밋(429): {body}")
            raise LLMUpstreamError(f"Groq 비정상 응답 {response.status_code}: {body}")

        # 논리상 도달하지 않음(위 for가 반드시 return 또는 raise). 방어적 처리.
        raise LLMUpstreamError("Groq 재시도 로직 예외(도달 불가)")

    def _backoff(self, attempt: int) -> float:
        """지수 백오프 + 지터(초). 동기화된 재폭주(thundering herd) 방지용 지터 포함."""
        return min(8.0, self._retry_base * (2 ** attempt)) + random.uniform(0.0, 0.3)

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        """서버가 Retry-After를 주면 존중(상한 30s), 없으면 지수 백오프."""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except (TypeError, ValueError):
                pass
        return self._backoff(attempt)
