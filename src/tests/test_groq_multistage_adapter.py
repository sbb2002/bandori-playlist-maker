"""GroqMultistageMoodInterpreter 테스트 — HTTP를 목킹한다(실제 호출 금지, tests/README §3).

test_groq_adapter.py와 동일한 목 패턴을 재사용한다. 이 파일이 다루는 것: 1차(재생시간)→
2차(구간 분할)→3차(구간별 에너지) 3회 순차 호출의 파싱·클램프·재시도 로직
(topic/llm-param-control-separate/backgroud.md).
"""

import httpx
import pytest

from app.adapters.groq_multistage_adapter import GroqMultistageMoodInterpreter
from app.ports.mood_port import LLMRateLimitError, LLMUpstreamError, MoodInterpretationError


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.headers = {}

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakeClient:
    """순차 응답(responses=[...])을 스테이지 호출 순서대로 반환하는 목 클라이언트."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._responses.pop(0)


def _chat(content: str) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": content}}]})


def _make(responses, max_retries=0, stage_retries=0) -> GroqMultistageMoodInterpreter:
    client = FakeClient(responses)
    interp = GroqMultistageMoodInterpreter(
        api_key="test-key", model="test/model", client=client,
        max_retries=max_retries, retry_base=0.0, stage_retries=stage_retries,
    )
    return interp, client


_STAGE1_OK = "40"
_STAGE2_OK = "3\n15,잔잔한\n20,고조되는\n5,여운"
_STAGE3_OK = "0.20\n0.75\n0.35"


def test_success_assembles_mood_parameters():
    interp, client = _make([_chat(_STAGE1_OK), _chat(_STAGE2_OK), _chat(_STAGE3_OK)])
    params = interp.interpret("주말 드라이브 40분")

    assert params.target_minutes == 40
    assert params.stage_count == 3
    assert params.stage_energies == pytest.approx([0.20, 0.75, 0.35])
    assert params.start_energy == pytest.approx(0.20)
    assert params.end_energy == pytest.approx(0.35)
    assert params.brightness == 0.0
    assert params.song_type == "all"
    assert params.same_as_previous is None
    assert 2 <= len(params.tags) <= 5
    assert "잔잔한" in params.interpretation_summary
    assert "여운" in params.interpretation_summary
    assert len(client.calls) == 3


def test_stage1_clamps_out_of_range_minutes():
    interp, _ = _make([_chat("500"), _chat(_STAGE2_OK), _chat(_STAGE3_OK)])
    params = interp.interpret("긴 요청")
    assert params.target_minutes == 180  # _MINUTES_RANGE 상한 클램프


def test_stage2_extra_text_around_numbers_still_parses():
    messy = "구간 수는 3개입니다\n15분,잔잔한 시작\n20분,점점 고조\n5분,여운 마무리"
    interp, _ = _make([_chat(_STAGE1_OK), _chat(messy), _chat(_STAGE3_OK)])
    params = interp.interpret("x")
    assert params.stage_count == 3


def test_stage3_energy_values_are_clamped():
    # 파싱 정규식은 부호 없는 숫자만 잡는다(에너지는 정의상 0~1이라 음수 응답을 기대하지
    # 않음) — 상한(1.5→1.0) 클램프만 확인한다.
    interp, _ = _make([_chat(_STAGE1_OK), _chat(_STAGE2_OK), _chat("0.1\n1.5\n0.5")])
    params = interp.interpret("x")
    assert params.stage_energies == pytest.approx([0.1, 1.0, 0.5])


def test_stage1_unparseable_retries_then_succeeds():
    interp, client = _make(
        [_chat("모르겠어요"), _chat(_STAGE1_OK), _chat(_STAGE2_OK), _chat(_STAGE3_OK)],
        stage_retries=1,
    )
    params = interp.interpret("x")
    assert params.target_minutes == 40
    assert len(client.calls) == 4


def test_stage1_all_retries_exhausted_raises():
    interp, client = _make([_chat("모르겠어요"), _chat("여전히 모름")], stage_retries=1)
    with pytest.raises(MoodInterpretationError):
        interp.interpret("x")
    assert len(client.calls) == 2


def test_stage2_fewer_than_two_stages_raises():
    interp, _ = _make([_chat(_STAGE1_OK), _chat("1\n40,단조로운")], stage_retries=0)
    with pytest.raises(MoodInterpretationError):
        interp.interpret("x")


def test_stage3_insufficient_values_raises():
    interp, _ = _make([_chat(_STAGE1_OK), _chat(_STAGE2_OK), _chat("0.2\n0.5")], stage_retries=0)
    with pytest.raises(MoodInterpretationError):
        interp.interpret("x")


def test_429_raises_rate_limit_error():
    interp, client = _make([FakeResponse(429, text="slow down")])
    with pytest.raises(LLMRateLimitError):
        interp.interpret("x")
    assert len(client.calls) == 1


def test_network_error_raises_upstream():
    client = FakeClient([])
    client.post = lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("boom"))
    interp = GroqMultistageMoodInterpreter(api_key="k", model="m", client=client, max_retries=0)
    with pytest.raises(LLMUpstreamError):
        interp.interpret("x")


def test_empty_api_key_raises_value_error():
    with pytest.raises(ValueError):
        GroqMultistageMoodInterpreter(api_key="")
