"""스텁 어댑터 — 프롬프트 의도 동일성 휴리스틱(핫픽스: 세부설정 우선순위) 테스트."""

from app.adapters.stub_adapter import StubMoodInterpreter, _essentially_same


def test_essentially_same_identical():
    assert _essentially_same("차분한 곡", "차분한 곡") is True


def test_essentially_same_whitespace_and_case_insensitive():
    assert _essentially_same("  차분한   곡 ", "차분한 곡") is True


def test_essentially_same_different_intent():
    assert _essentially_same("신나는 파티 음악", "조용한 수면 음악") is False


def test_interpret_without_previous_leaves_same_none():
    # 1회차(직전 프롬프트 없음)에는 판정하지 않는다 → None.
    assert StubMoodInterpreter().interpret("아무거나").same_as_previous is None


def test_interpret_same_previous_is_true():
    assert StubMoodInterpreter().interpret("아무거나", "아무거나").same_as_previous is True


def test_interpret_different_previous_is_false():
    assert StubMoodInterpreter().interpret("신나는 파티", "조용한 수면 명상").same_as_previous is False
