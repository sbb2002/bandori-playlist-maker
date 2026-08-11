"""프롬프트 밴드명(별명) 자동 감지 테스트."""

from app.api.band_aliases import detect_bands


def test_detect_ras_and_mutype():
    assert detect_bands("RAS와 뮤타입 노래로 헬스로 불태울만한 노래") == {"raise_a_suilen", "mugendai_mutype"}


def test_detect_none_when_no_band():
    assert detect_bands("조용하고 잔잔한 플리 만들어줘") == set()


def test_detect_roselia_nickname():
    assert "roselia" in detect_bands("로제 노래 틀어줘")


def test_detect_popipa_nickname():
    assert "poppin_party" in detect_bands("포피파 신나는 곡으로")


def test_detect_english_name():
    assert "afterglow" in detect_bands("afterglow 감성으로")


def test_no_false_positive_on_playlist_keyword():
    """2026-08-11 버그 픽스: '플레이리스트'는 예전엔 RAISE A SUILEN 별명 '레이'와 부분
    문자열이 겹쳐 밴드 언급이 전혀 없어도 오탐됐다(앱 핵심 단어라 상시 발동하는 영향 큰
    버그) — '레이' 제거 후 재발 방지 회귀 테스트."""
    assert detect_bands("집중력 올려주는 플레이리스트 만들어줘") == set()
    assert detect_bands("기분 좋아지는 플레이리스트 하나 뽑아줘") == set()


def test_ras_still_detected_by_remaining_short_alias():
    assert "raise_a_suilen" in detect_bands("라스 노래로 신나게")
