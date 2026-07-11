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
