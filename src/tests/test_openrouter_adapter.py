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


def test_parse_stage_params_matching_length_kept_and_clamped():
    """3단계: stage_count와 길이가 같으면 stage_params를 살리고, 범위 밖 값은 클램프한다."""
    from app.adapters.prompt import parse_mood
    p = parse_mood(
        '{"brightness":0.3,"start_energy":0.3,"end_energy":0.4,"stage_count":2,'
        '"stage_params":['
        '{"valence":0.8,"lufs_integrated":5,"lra":null},'
        '{"valence":-1,"instr_stem_ratio":0.4}'
        '],"target_minutes":45,"interpretation_summary":""}'
    )
    assert p.stage_params == [
        {"valence": 0.8, "lufs_integrated": 1.0, "lra": None,
         "danceability_norm": None, "instr_stem_ratio": None, "speech_median": None,
         "impression": None},
        {"valence": 0.0, "lufs_integrated": None, "lra": None,
         "danceability_norm": None, "instr_stem_ratio": 0.4, "speech_median": None,
         "impression": None},
    ]


def test_parse_stage_params_impression_kept_and_truncated():
    """프로토타입: impression은 6개 수치와 별도로 파싱되고, 최대 길이를 넘으면 잘린다."""
    from app.adapters.prompt import _IMPRESSION_MAX_LEN, parse_mood
    long_text = "가" * (_IMPRESSION_MAX_LEN + 20)
    p = parse_mood(
        '{"brightness":0.3,"start_energy":0.3,"end_energy":0.4,"stage_count":2,'
        '"stage_params":['
        '{"valence":0.5,"impression":"  차분하고 그리운 정서  "},'
        '{"valence":0.5,"impression":"' + long_text + '"}'
        '],"target_minutes":45,"interpretation_summary":""}'
    )
    assert p.stage_params[0]["impression"] == "차분하고 그리운 정서"  # 앞뒤 공백 정리
    assert p.stage_params[1]["impression"] == long_text[:_IMPRESSION_MAX_LEN]


def test_parse_stage_params_impression_blank_or_missing_is_none():
    from app.adapters.prompt import parse_mood
    p = parse_mood(
        '{"brightness":0,"start_energy":0.4,"end_energy":0.4,"stage_count":2,'
        '"stage_params":[{"valence":0.5,"impression":"   "},{"valence":0.5}],'
        '"target_minutes":null,"interpretation_summary":""}'
    )
    assert p.stage_params[0]["impression"] is None
    assert p.stage_params[1]["impression"] is None


def test_parse_stage_params_length_mismatch_dropped():
    """stage_count(3)와 배열 길이(2)가 안 맞으면 통째로 None 폴백(부분 신뢰 안 함)."""
    from app.adapters.prompt import parse_mood
    p = parse_mood(
        '{"brightness":0,"start_energy":0.4,"end_energy":0.4,"stage_count":3,'
        '"stage_params":[{"valence":0.5},{"valence":0.6}],'
        '"target_minutes":null,"interpretation_summary":""}'
    )
    assert p.stage_params is None


def test_parse_stage_params_absent_is_none():
    from app.adapters.prompt import parse_mood
    assert parse_mood(_OK_JSON).stage_params is None


def test_parse_stage_minutes_matching_length_kept_and_floored():
    """3.5단계: stage_count와 길이가 같으면 유지, 하한(3분) 아래 값은 올림 클램프."""
    from app.adapters.prompt import parse_mood
    p = parse_mood(
        '{"brightness":0,"start_energy":0.4,"end_energy":0.4,"stage_count":3,'
        '"stage_minutes":[1,20,15],"target_minutes":40,"interpretation_summary":""}'
    )
    assert p.stage_minutes == [3.0, 20.0, 15.0]


def test_parse_stage_minutes_length_mismatch_dropped():
    from app.adapters.prompt import parse_mood
    p = parse_mood(
        '{"brightness":0,"start_energy":0.4,"end_energy":0.4,"stage_count":3,'
        '"stage_minutes":[10,20],"target_minutes":40,"interpretation_summary":""}'
    )
    assert p.stage_minutes is None


def test_parse_stage_minutes_absent_is_none():
    from app.adapters.prompt import parse_mood
    assert parse_mood(_OK_JSON).stage_minutes is None


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


# ── previous_prompt/same_as_previous DEPRECATED(2026-08-11): AI/커스텀 모드 분리 후
# 라우팅에서 안 쓰여 프롬프트 생성 단계에서도 완전히 무시한다 ────────────────────────
def test_build_messages_ignores_previous_prompt():
    from app.adapters.prompt import build_messages
    with_prev = build_messages("현재 요청 텍스트", "직전 요청 텍스트")[-1]["content"]
    assert with_prev == "현재 요청 텍스트"
    assert "직전 요청" not in with_prev


def test_build_messages_without_previous_is_plain():
    from app.adapters.prompt import build_messages
    assert build_messages("현재 요청 텍스트")[-1]["content"] == "현재 요청 텍스트"


# ── 예시 숫자 jitter(3.5단계 함정 수정: 모델이 프롬프트 예시를 그대로 복사하던 문제) ──────────

def test_dynamic_examples_are_jittered_across_calls():
    """예시 stage_params 숫자가 매 호출마다 달라야 모델이 그대로 베끼는 걸 막을 수 있다."""
    from app.adapters.prompt import build_messages
    system_a = build_messages("x")[0]["content"]
    system_b = build_messages("x")[0]["content"]
    assert system_a != system_b


def test_jitter_stage_params_stays_in_bounds():
    from app.adapters.prompt import _BALLAD_EXAMPLE_TEMPLATE, _jitter_stage_params
    import random
    rng = random.Random(0)
    for _ in range(50):
        jittered = _jitter_stage_params(_BALLAD_EXAMPLE_TEMPLATE, rng)
        assert all(0.0 <= v <= 1.0 for v in jittered.values())


def test_parse_mood_same_as_previous_always_none_even_if_present():
    from app.adapters.prompt import parse_mood
    p = parse_mood('{"brightness":0,"start_energy":0.4,"end_energy":0.4,"stage_count":3,'
                   '"target_minutes":null,"interpretation_summary":"","same_as_previous":true}')
    assert p.same_as_previous is None


def test_parse_mood_same_as_previous_absent_is_none():
    from app.adapters.prompt import parse_mood
    assert parse_mood(_OK_JSON).same_as_previous is None


def test_interpret_does_not_forward_previous_prompt():
    client = FakeClient(response=_chat_response(_OK_JSON))
    _make(client).interpret("현재 요청", "직전 요청")
    sent = client.calls[0]["json"]["messages"][-1]["content"]
    assert "현재 요청" in sent and "직전 요청" not in sent
