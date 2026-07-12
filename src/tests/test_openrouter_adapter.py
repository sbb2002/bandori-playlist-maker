"""OpenRouter 어댑터 테스트 — HTTP를 목킹한다(실제 호출 금지, tests/README §3)."""

import httpx
import pytest

import app.adapters.openrouter_adapter as orad
from app.adapters.openrouter_adapter import OpenRouterMoodInterpreter
from app.ports.mood_port import (
    LLMRateLimitError,
    LLMUpstreamError,
    MoodInterpretationError,
)


class FakeResponse:
    def __init__(self, status_code, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakeClient:
    """httpx.Client.post 시그니처만 흉내내는 목 클라이언트. responses=[...]로 순차 응답."""

    def __init__(self, response=None, exc=None, responses=None):
        self._response = response
        self._exc = exc
        self._responses = list(responses) if responses is not None else None
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._exc is not None:
            raise self._exc
        if self._responses is not None:
            return self._responses.pop(0)
        return self._response


def _chat_response(content: str) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


_OK_JSON = ('{"brightness":0,"start_energy":0.4,"end_energy":0.4,'
            '"stage_count":3,"target_minutes":null,"interpretation_summary":""}')


def _make(client, max_retries=0) -> OpenRouterMoodInterpreter:
    # 기본 max_retries=0 → 기존 테스트는 단일 호출(빠름·즉시). 재시도 테스트만 명시적으로 올린다.
    return OpenRouterMoodInterpreter(
        api_key="test-key", model="test/model", client=client,
        max_retries=max_retries, retry_base=0.0,
    )


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


def test_parse_stage_energies_nonmonotonic():
    from app.adapters.prompt import parse_mood
    p = parse_mood(
        '{"brightness":0.3,"start_energy":0.3,"end_energy":0.4,"stage_count":4,'
        '"stage_energies":[0.3,0.85,0.85,0.4],"target_minutes":45,"interpretation_summary":"유산소"}'
    )
    assert p.stage_energies == [0.3, 0.85, 0.85, 0.4]


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


def test_non_retryable_non_200_raises_upstream():
    interp = _make(FakeClient(response=FakeResponse(400, text="bad request")))
    with pytest.raises(LLMUpstreamError):
        interp.interpret("x")


def test_429_raises_rate_limit_error():
    interp = _make(FakeClient(response=FakeResponse(429, text="rate limited")))
    with pytest.raises(LLMRateLimitError):
        interp.interpret("x")


def test_persistent_429_retries_then_raises(monkeypatch):
    monkeypatch.setattr(orad.time, "sleep", lambda *a, **k: None)
    client = FakeClient(response=FakeResponse(429, text="slow down"))
    with pytest.raises(LLMRateLimitError):
        _make(client, max_retries=2).interpret("x")
    assert len(client.calls) == 3  # 최초 + 2 재시도


def test_429_then_success(monkeypatch):
    monkeypatch.setattr(orad.time, "sleep", lambda *a, **k: None)
    client = FakeClient(responses=[FakeResponse(429, text="wait"), _chat_response(_OK_JSON)])
    params = _make(client, max_retries=2).interpret("x")
    assert params.stage_count == 3
    assert len(client.calls) == 2


def test_5xx_then_success(monkeypatch):
    monkeypatch.setattr(orad.time, "sleep", lambda *a, **k: None)
    client = FakeClient(responses=[FakeResponse(503, text="unavailable"), _chat_response(_OK_JSON)])
    params = _make(client, max_retries=1).interpret("x")
    assert params.stage_count == 3
    assert len(client.calls) == 2


def test_retry_after_header_honored(monkeypatch):
    slept = []
    monkeypatch.setattr(orad.time, "sleep", lambda s: slept.append(s))
    client = FakeClient(responses=[
        FakeResponse(429, text="wait", headers={"Retry-After": "2"}),
        _chat_response(_OK_JSON),
    ])
    _make(client, max_retries=1).interpret("x")
    assert slept == [2.0]  # Retry-After(초) 존중


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


# ── 프롬프트 의도 동일성(핫픽스: 세부설정 우선순위) ───────────────────────────────
def test_build_messages_includes_previous_prompt():
    from app.adapters.prompt import build_messages
    user = build_messages("현재 요청 텍스트", "직전 요청 텍스트")[-1]["content"]
    assert "직전 요청 텍스트" in user and "현재 요청 텍스트" in user and "same_as_previous" in user


def test_build_messages_without_previous_is_plain():
    from app.adapters.prompt import build_messages
    assert build_messages("현재 요청 텍스트")[-1]["content"] == "현재 요청 텍스트"


def test_parse_mood_same_as_previous_extracted():
    from app.adapters.prompt import parse_mood
    p = parse_mood('{"brightness":0,"start_energy":0.4,"end_energy":0.4,"stage_count":3,'
                   '"target_minutes":null,"interpretation_summary":"","same_as_previous":true}')
    assert p.same_as_previous is True


def test_parse_mood_same_as_previous_absent_is_none():
    from app.adapters.prompt import parse_mood
    assert parse_mood(_OK_JSON).same_as_previous is None


def test_interpret_forwards_previous_prompt():
    client = FakeClient(response=_chat_response(_OK_JSON))
    _make(client).interpret("현재 요청", "직전 요청")
    sent = client.calls[0]["json"]["messages"][-1]["content"]
    assert "현재 요청" in sent and "직전 요청" in sent
