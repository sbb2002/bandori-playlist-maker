"""OpenRouter 어댑터 테스트 — HTTP를 목킹한다(실제 호출 금지, tests/README §3)."""

import httpx
import pytest

from app.adapters.openrouter_adapter import OpenRouterMoodInterpreter
from app.ports.mood_port import LLMUpstreamError, MoodInterpretationError


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakeClient:
    """httpx.Client.post 시그니처만 흉내내는 목 클라이언트."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._exc is not None:
            raise self._exc
        return self._response


def _chat_response(content: str) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def _make(client) -> OpenRouterMoodInterpreter:
    return OpenRouterMoodInterpreter(api_key="test-key", model="test/model", client=client)


def test_success_parses_mood():
    content = ('{"brightness":0.7,"start_energy":0.35,"end_energy":0.85,'
               '"stage_count":3,"target_minutes":60,"interpretation_summary":"밝게 고조"}')
    interp = _make(FakeClient(response=_chat_response(content)))
    params = interp.interpret("주말 신나는 1시간")
    assert params.brightness == pytest.approx(0.7)
    assert params.start_energy == pytest.approx(0.35)
    assert params.end_energy == pytest.approx(0.85)
    assert params.stage_count == 3
    assert params.target_minutes == 60


def test_markdown_fenced_json_is_parsed():
    content = '```json\n{"brightness":0.2,"start_energy":0.5,"end_energy":0.5,"stage_count":2,"target_minutes":null,"interpretation_summary":""}\n```'
    interp = _make(FakeClient(response=_chat_response(content)))
    params = interp.interpret("차분하게")
    assert params.stage_count == 2
    assert params.target_minutes is None


def test_out_of_range_values_clamped():
    content = ('{"brightness":5,"start_energy":-2,"end_energy":9,'
               '"stage_count":99,"target_minutes":9999,"interpretation_summary":""}')
    interp = _make(FakeClient(response=_chat_response(content)))
    params = interp.interpret("x")
    assert params.brightness == 1.0
    assert params.start_energy == 0.0
    assert params.end_energy == 1.0
    assert params.stage_count == 5
    assert params.target_minutes == 180


def test_auth_header_sent():
    client = FakeClient(response=_chat_response(
        '{"brightness":0,"start_energy":0.4,"end_energy":0.4,"stage_count":3,"target_minutes":null,"interpretation_summary":""}'))
    _make(client).interpret("x")
    assert client.calls[0]["headers"]["Authorization"] == "Bearer test-key"


def test_non_200_raises_upstream():
    interp = _make(FakeClient(response=FakeResponse(429, text="rate limited")))
    with pytest.raises(LLMUpstreamError):
        interp.interpret("x")


def test_network_error_raises_upstream():
    interp = _make(FakeClient(exc=httpx.ConnectError("boom")))
    with pytest.raises(LLMUpstreamError):
        interp.interpret("x")


def test_missing_choices_raises_mood_error():
    interp = _make(FakeClient(response=FakeResponse(200, {"unexpected": True})))
    with pytest.raises(MoodInterpretationError):
        interp.interpret("x")


def test_empty_content_raises_mood_error():
    interp = _make(FakeClient(response=_chat_response("   ")))
    with pytest.raises(MoodInterpretationError):
        interp.interpret("x")


def test_unparseable_content_raises_mood_error():
    interp = _make(FakeClient(response=_chat_response("이건 JSON이 아니에요")))
    with pytest.raises(MoodInterpretationError):
        interp.interpret("x")
