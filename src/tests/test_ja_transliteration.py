"""곡 제목 로마자/한글 음차 변환 테스트(검색 보조 필드, ja_transliteration.py)."""

from app.repo.ja_transliteration import kana_to_hangul, to_hangul, to_romaji


def test_to_romaji_basic_hiragana():
    assert to_romaji("さくら") == "sakura"


def test_to_romaji_passes_through_ascii():
    assert to_romaji("Roselia") == "Roselia"


def test_to_hangul_basic():
    assert to_hangul("さくら") == "사구라"


def test_to_hangul_handles_sokuon_geminate():
    # 촉음(っ) → 앞 음절에 ㅅ받침.
    assert kana_to_hangul("はっぴー") == "핫피이"


def test_to_hangul_handles_hatsuon_n():
    # 발음(ん) → 앞 음절에 ㄴ받침(단순화).
    assert kana_to_hangul("さんた") == "산타"


def test_to_hangul_handles_long_vowel_mark():
    # 장음(ー) → 직전 음절 모음 반복.
    assert kana_to_hangul("らあめん") == kana_to_hangul("らーめん")


def test_to_hangul_handles_youon_digraph():
    assert kana_to_hangul("きゃ") == "갸"


def test_to_hangul_passes_through_unmapped_chars():
    # 매핑 밖 문자(기호 등)는 원문 그대로 통과.
    assert kana_to_hangul("！") == "！"


def test_real_song_title_does_not_crash_and_is_nonempty():
    title = "ハピネスっ！ハピィーマジカルっ♪"
    assert to_romaji(title)
    assert to_hangul(title)
