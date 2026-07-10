"""하모닉 호환 판정 테스트 (도메인 순수 — 네트워크·LLM 없음)."""

from app.domain.harmonic import harmonic_label, is_compatible


def test_same_camelot_is_compatible():
    assert is_compatible("8A", "8A") is True


def test_adjacent_codes_compatible():
    # 8A의 인접: 8B(관계조), 7A·9A(같은 문자 ±1)
    assert is_compatible("8A", "8B")
    assert is_compatible("8A", "7A")
    assert is_compatible("8A", "9A")


def test_non_adjacent_not_compatible():
    assert is_compatible("8A", "3B") is False


def test_wrap_around_12_to_1():
    assert is_compatible("12A", "1A")
    assert is_compatible("1A", "12A")


def test_labels():
    assert harmonic_label(None, "8A") == "seed"
    assert harmonic_label("8A", "8A") == "same"
    assert harmonic_label("8A", "8B") == "adjacent"
    assert harmonic_label("8A", "3B") == "non_harmonic"
