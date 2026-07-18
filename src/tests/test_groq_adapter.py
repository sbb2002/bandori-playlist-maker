"""Groq 어댑터 테스트 — HTTP를 목킹한다(실제 호출 금지, tests/README §3).

test_openrouter_adapter.py와 동일한 목 패턴을 재사용한다. 이 파일이 특히 다루는 것:
무드 파싱 실패(200 응답인데 content가 JSON으로 안 풀리는 경우) 재시도(GROQ_MOOD_RETRIES,
hotfix/energy-graph-stage-sync) — 429/5xx 재시도(_post_with_retry)와는 별개 경로다.
"""

import httpx
import pytest

import app.adapters.groq_adapter as groq_ad
from app.adapters.groq_adapter import GroqMoodInterpreter
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


def _make(client, max_retries=0, mood_parse_retries=0) -> GroqMoodInterpreter:
    # 기본값은 재시도 0 → 기존 동작 테스트는 단일 호출(빠름·즉시). 재시도 테스트만 명시적으로 올린다.
    return GroqMoodInterpreter(
        api_key="test-key", model="test/model", client=client,
        max_retries=max_retries, retry_base=0.0, mood_parse_retries=mood_parse_retries,
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


def test_auth_header_sent():
    client = FakeClient(response=_chat_response(_OK_JSON))
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


# ── 무드 파싱 재시도(GROQ_MOOD_RETRIES) ────────────────────────────────────────
# 디테일한 다단계 절대시간 요청("10분에 중간, 20분에 높게, 30분에 최고조...")에서 모델이
# 간헐적으로 JSON이 아닌 텍스트를 섞어 내보내는 경우를 흉내낸다. 200 응답 자체는 정상이라
# _post_with_retry(429/5xx 대상)는 개입하지 않고, mood_parse_retries 루프만 재시도해야 한다.

def test_unparseable_then_success_retries_and_returns_params():
    client = FakeClient(responses=[
        _chat_response("죄송해요, 이 요청은 무드로 정리하기 어려워요"),  # 1차: 파싱 실패
        _chat_response("또 실패하는 응답입니다"),  # 2차: 파싱 실패
        _chat_response(_OK_JSON),  # 3차: 성공
    ])
    params = _make(client, mood_parse_retries=3).interpret(
        "천천히 워밍업해서 10분즈음에 중간, 20분쯤에 높게, 30분쯤에 최고조에 달하게 해주고 "
        "그 뒤에 37분까지 마무리하도록 쿨다운하게 도와줘"
    )
    assert params.stage_count == 3
    assert len(client.calls) == 3  # 1차·2차 실패 + 3차 성공


def test_all_mood_parse_retries_exhausted_raises_same_as_before():
    client = FakeClient(response=_chat_response("계속 JSON이 아닌 응답"))
    with pytest.raises(MoodInterpretationError):
        _make(client, mood_parse_retries=3).interpret("x")
    assert len(client.calls) == 4  # 최초 1회 + 재시도 3회, 그 이상 재호출하지 않음


def test_mood_parse_retries_zero_means_single_attempt():
    client = FakeClient(response=_chat_response("JSON 아님"))
    with pytest.raises(MoodInterpretationError):
        _make(client, mood_parse_retries=0).interpret("x")
    assert len(client.calls) == 1  # 재시도 비활성화 시 기존과 동일(단일 호출)


def test_mood_parse_retry_does_not_retry_rate_limit_error():
    # 429는 _post_with_retry가 이미 소진 후 던지는 것 — mood_parse 루프가 이걸 다시 삼켜
    # 429를 mood_parse_retries만큼 추가로 재시도하면 안 된다(레이트리밋 상태에서 폭주 위험).
    client = FakeClient(response=FakeResponse(429, text="slow down"))
    with pytest.raises(LLMRateLimitError):
        _make(client, max_retries=0, mood_parse_retries=3).interpret("x")
    assert len(client.calls) == 1


def test_default_mood_parse_retries_is_three():
    client = FakeClient(response=_chat_response("JSON 아님"))
    interp = GroqMoodInterpreter(api_key="test-key", model="test/model", client=client, retry_base=0.0)
    with pytest.raises(MoodInterpretationError):
        interp.interpret("x")
    assert len(client.calls) == 4  # 기본값 3회 재시도 확인(최초 1 + 재시도 3)
