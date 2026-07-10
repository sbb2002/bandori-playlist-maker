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
DEFAULT_MODEL = "openai/gpt-4o-mini"  # 경량 구조화 추출용 1차 후보(§④-3). env로 교체 가능.
DEFAULT_TIMEOUT = 30.0


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
            "response_format": prompt_mod.RESPONSE_JSON_SCHEMA,
        }
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
