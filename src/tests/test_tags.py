"""요약 카드 해시태그 최소 보장 테스트 — LLM이 태그를 비워도 2~5개가 나와야 한다."""

import json

from app.adapters.prompt import parse_mood
from app.adapters.stub_adapter import StubMoodInterpreter
from app.domain.tags import MAX_TAGS, MIN_TAGS, derive_tags, ensure_min_tags


def test_ensure_min_tags_fills_when_empty():
    """태그가 없으면 파생 키워드로 최소 개수까지 채운다."""
    for existing in (None, [], ["#"], ["   "]):
        out = ensure_min_tags(existing, brightness=0.0, start_energy=0.4, end_energy=0.4)
        assert MIN_TAGS <= len(out) <= MAX_TAGS
        assert all(t and not t.startswith("#") for t in out)


def test_ensure_min_tags_respects_existing_and_order():
    """이미 최소 개수 이상이면 파생 없이 원본을 (중복 제거해) 유지한다."""
    existing = ["드라이브", "설렘", "주말"]
    out = ensure_min_tags(existing, brightness=0.9, start_energy=0.8, end_energy=0.9)
    assert out == existing


def test_ensure_min_tags_supplements_single():
    """1개만 있으면 원본을 앞에 두고 부족분만 파생으로 채운다."""
    out = ensure_min_tags(["드라이브"], brightness=0.9, start_energy=0.8, end_energy=0.9)
    assert out[0] == "드라이브"
    assert len(out) >= MIN_TAGS


def test_ensure_min_tags_dedupes_case_and_hash():
    """대소문자·선행 # 차이는 중복으로 보고 제거한다."""
    out = ensure_min_tags(["Drive", "#drive", "설렘"], brightness=0.0, start_energy=0.4, end_energy=0.4)
    lowered = [t.lower() for t in out]
    assert len(lowered) == len(set(lowered))
    assert "drive" in lowered


def test_ensure_min_tags_caps_at_maximum():
    """상한을 넘는 입력은 maximum으로 자른다."""
    many = [f"태그{i}" for i in range(9)]
    out = ensure_min_tags(many, brightness=0.0, start_energy=0.4, end_energy=0.4)
    assert len(out) == MAX_TAGS


def test_derive_tags_never_below_minimum_even_neutral():
    """모든 축이 중립(가장 밋밋한 요청)이어도 후보가 최소 개수 이상 나온다."""
    candidates = derive_tags(brightness=0.0, start_energy=0.4, end_energy=0.4)
    # 대소문자 무시 중복 제거 후에도 최소치 이상이어야 채움이 항상 성공한다.
    distinct = {c.lower() for c in candidates}
    assert len(distinct) >= MIN_TAGS


def test_parse_mood_guarantees_tags_when_llm_omits():
    """LLM 응답에 tags가 없거나 빈 배열이어도 parse_mood는 2~5개를 채운다."""
    for body in (
        {"brightness": 0.6, "start_energy": 0.5, "end_energy": 0.7},
        {"brightness": 0.6, "start_energy": 0.5, "end_energy": 0.7, "tags": []},
        {"brightness": -0.5, "start_energy": 0.2, "end_energy": 0.2, "tags": None},
    ):
        params = parse_mood(json.dumps(body, ensure_ascii=False))
        assert params.tags is not None
        assert MIN_TAGS <= len(params.tags) <= MAX_TAGS


def test_stub_interpreter_emits_min_tags():
    """스텁 어댑터도 요약 카드용으로 최소 2개 태그를 낸다."""
    params = StubMoodInterpreter().interpret("적당한 플레이리스트")
    assert params.tags is not None
    assert MIN_TAGS <= len(params.tags) <= MAX_TAGS
