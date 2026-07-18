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


# ── 회귀: 실제 llama-3.1-8b-instant 로컬 테스트에서 관측된 패턴 ─────────────────
# "숫자만 답해" 지시를 무시하고 장문 설명을 앞세우는 모델이라, 마커 이전 텍스트에 나온
# 숫자(요청 인용 등)를 정답으로 잘못 집지 않는지 확인한다.

def test_stage1_ignores_numbers_in_reasoning_preamble_before_marker():
    verbose = (
        "5km 러닝을 위한 플레이리스트라면 보통 30~45분 정도가 적당합니다. "
        "천천히 시작해서 점점 빨라지는 구성을 고려하면 40분이 적절해 보입니다.\n\n"
        "===ANSWER===\n40"
    )
    interp, _ = _make([_chat(verbose), _chat(_STAGE2_OK), _chat(_STAGE3_OK)])
    params = interp.interpret("5km 러닝")
    assert params.target_minutes == 40  # 서두의 "5km"의 5나 "30~45"가 아니라 마커 뒤 40


def test_stage3_ignores_numbered_list_prefix_before_marker():
    # 실측 패턴: 마커 앞에서 "1. 잔잔한: ... 0.05로 설정" 식으로 번호+설명을 붙이고,
    # 마커 뒤에는 지시대로 값만 순서대로 나열.
    verbose = (
        "1. 잔잔한: 도입부라 낮게, 0.05 근처로 설정.\n"
        "2. 고조되는: 점점 올라가는 구간, 0.70 정도.\n"
        "3. 여운: 마무리라 다시 낮게, 0.40 근처.\n\n"
        "===ANSWER===\n0.05\n0.70\n0.40"
    )
    interp, _ = _make([_chat(_STAGE1_OK), _chat(_STAGE2_OK), _chat(verbose)])
    params = interp.interpret("x")
    assert params.stage_energies == pytest.approx([0.05, 0.70, 0.40])


def test_stage2_marker_skips_reasoning_preamble():
    verbose = (
        "먼저 도입부는 잔잔하게 6분 정도, 그 다음은 신나게 올리고...\n"
        "고민 끝에 아래처럼 정리합니다.\n\n"
        "===ANSWER===\n2\n15,잔잔한\n25,신나는"
    )
    interp, _ = _make([_chat(_STAGE1_OK), _chat(verbose), _chat("0.2\n0.8")])
    params = interp.interpret("x")
    assert params.stage_count == 2
    assert params.stage_energies == pytest.approx([0.2, 0.8])


def test_stage1_no_marker_falls_back_to_last_number_in_text():
    # 마커를 아예 안 붙인 경우: 결론이 보통 끝에 오므로 "마지막" 숫자를 취해야
    # 서두의 "5km" 같은 요청 인용 숫자를 오답으로 집지 않는다.
    no_marker = "5km 정도 되는 러닝이라면 대략 40분짜리 플레이리스트가 좋겠습니다."
    interp, _ = _make([_chat(no_marker), _chat(_STAGE2_OK), _chat(_STAGE3_OK)])
    params = interp.interpret("x")
    assert params.target_minutes == 40
