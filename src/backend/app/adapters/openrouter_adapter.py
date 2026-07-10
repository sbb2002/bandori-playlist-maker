"""OpenRouter 어댑터 — MoodInterpreter 포트의 운영 구현.

벤더/모델 교체 시 이 파일(과 main.py 주입 1줄)만 교체하면 된다. HTTP 세부는 여기에만 존재하며
도메인·API는 이 모듈을 모른다. 파싱/검증은 `prompt.py`에 위임한다.
"""

from __future__ import annotations

import httpx

from ..domain.models import MoodParameters
from ..ports.mood_port import LLMUpstreamError, MoodInterpretationError
from . import prompt as prompt_mod

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
# 파일럿 기본: 무료 경량 모델(사용자 결정 — §④-3/§9 모델 오픈퀘스천 확정). env로 교체 가능.
# 참고: reasoning 모델이라 응답이 다소 느릴 수 있으나 추출 정확도·비용(무료) 양호.
DEFAULT_MODEL = "nvidia/nemotron-3-nano-30b-a3b:free"
DEFAULT_TIMEOUT = 60.0  # 무료/reasoning 모델 지연 감안


class OpenRouterMoodInterpreter:
    """OpenRouter chat/completions로 무드를 해석하는 MoodInterpreter 구현."""

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
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter api_key가 비어 있습니다.")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # 주입 가능한 클라이언트(테스트 목킹용). 없으면 자체 생성.
        self._client = client or httpx.Client(timeout=timeout)
        self._referer = referer
        self._title = title
        # 응답 포맷 강제 모드: "none"(전 모델 호환, 프롬프트+관용 파서에 의존) |
        # "json_object"(JSON 모드) | "json_schema"(structured output — 지원 모델만).
        self._response_format_mode = response_format_mode.strip().lower()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": self._title,
        }
        # OpenRouter 랭킹/식별용(선택). GitHub Pages 오리진 등.
        if self._referer:
            headers["HTTP-Referer"] = self._referer
        return headers

    def interpret(self, prompt: str) -> MoodParameters:
        payload = {
            "model": self._model,
            "messages": prompt_mod.build_messages(prompt),
            "temperature": 0.2,
        }
        if self._response_format_mode == "json_schema":
            payload["response_format"] = prompt_mod.RESPONSE_JSON_SCHEMA
        elif self._response_format_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        # "none": response_format 미전송 — 강한 시스템 프롬프트 + 관용 파서로 처리(전 모델 호환).
        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMUpstreamError(f"OpenRouter 요청 실패: {exc}") from exc

        if response.status_code != 200:
            raise LLMUpstreamError(
                f"OpenRouter 비정상 응답 {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise MoodInterpretationError(f"OpenRouter 응답 구조 예상 밖: {exc}") from exc

        if not isinstance(content, str) or not content.strip():
            raise MoodInterpretationError("OpenRouter 응답 content가 비어 있습니다.")

        return prompt_mod.parse_mood(content)
