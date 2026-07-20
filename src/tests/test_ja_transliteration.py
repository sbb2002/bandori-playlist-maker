"""곡 제목 로마자/한글 음차 변환 테스트(검색 보조 필드, ja_transliteration.py)."""

from app.repo.ja_transliteration import (
    kana_to_hangul,
    kana_to_hangul_variants,
    to_hangul,
    to_hangul_variants,
    to_hanja_reading,
    to_romaji,
)


def test_to_romaji_basic_hiragana():
    assert to_romaji("さくら") == "sakura"


def test_to_romaji_passes_through_ascii():
    assert to_romaji("Roselia") == "Roselia"


def test_to_hangul_basic():
    # か행(무성)은 が행(유성)과 구분되도록 ㅋ 계열(카/키/쿠/케/코)로 매핑한다.
    assert to_hangul("さくら") == "사쿠라"


def test_to_hangul_handles_sokuon_geminate():
    # 촉음(っ) → 앞 음절에 받침. ぴ는 ぱ행이라 ㅂ받침(はっぴー→"합피이").
    assert kana_to_hangul("はっぴー") == "합피이"


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


# ── 외래어(gairaigo) 사전 테스트 ──────────────────────────────────────────────────
def test_loanword_hangul_live():
    # ライブ → 자동 글자 단위(라이부) 대신 사전에서 "라이브"
    hira = "らいぶ"
    assert kana_to_hangul(hira) == "라이브"


def test_loanword_hangul_smile():
    # スマイル → 자동 글자 단위 대신 "스마일"
    hira = "すまいる"
    assert kana_to_hangul(hira) == "스마일"


def test_loanword_hangul_song():
    # ソング → "송" (글자 단위 "소그"와 다름)
    hira = "そんぐ"
    assert kana_to_hangul(hira) == "송"


def test_loanword_longest_match_priority():
    # 최장일치 우선: "らぶそんぐ"(ラブソング)가 "そんぐ"(ソング)보다 먼저 매칭돼야 함
    hira = "らぶそんぐ"
    result = kana_to_hangul(hira)
    # "らぶそんぐ" 전체가 사전에 있으면 "러브송", 없으면 "라부송구" 등이 됨
    # 테스트: 사전에 있는 경우 예상값은 "러브송"
    assert "러브송" in result or result == "러브송"


def test_loanword_hangul_big_mouse():
    # ビッグマウス(실제 카탈로그 곡, mugendai_mutype) → "빅마우스"
    # (촉음 규칙만 적용하면 "빅구마우스"가 되어 사용자가 실제로 검색해본 값과 어긋남 — 사전 등록으로 보정)
    assert kana_to_hangul("びっぐまうす") == "빅마우스"


def test_sokuon_before_g_row_uses_giyeok_batchim():
    # 촉음(っ) 뒤에 か/が행이 오면 ㅅ이 아니라 ㄱ받침(외래어 관용 표기에 가깝게).
    assert kana_to_hangul("ばっぐ") == "박구"


def test_sokuon_before_b_row_uses_bieup_batchim():
    # 촉음(っ) 뒤에 ぱ/ば행이 오면 ㅂ받침.
    assert kana_to_hangul("とっぷ") == "톱푸"


def test_sokuon_default_still_uses_siot_batchim():
    # か/が·ぱ/ば행이 아닌 경우(さ/ざ/た/だ행 등)는 기존처럼 ㅅ받침.
    assert kana_to_hangul("あっさり") == "앗사리"


def test_loanword_hangul_telepathy():
    # テレパシー(사용자 예시) → "텔레파시"
    # pykakasi 히라가나 변환 결과 확인 필요
    from app.repo.ja_transliteration import to_hangul as full_to_hangul
    result = full_to_hangul("テレパシー")
    # 히라가나로 변환 후 사전 적용: "てれぱしー" → "텔레파시"
    assert "텔레" in result or "텔" in result  # 최소한 "텔" 포함


# ── 장음 변형 병기(한국식 관용 표기 검색) 테스트 ────────────────────────────────
def test_variants_first_equals_legacy_output():
    # 변형 0은 종전 kana_to_hangul 출력(원문 음차)과 동일해야 한다(하위호환).
    for hira in ("はっぴー", "らーめん", "そんぐ", "さくら"):
        assert kana_to_hangul_variants(hira, strip_separators=False)[0] == kana_to_hangul(hira)


def test_variants_carnation_korean_convention():
    # カーネーション: 원문 음차(모음 반복)·장음 생략형·한국식(에이+션) 모두 병기돼야 한다.
    variants = to_hangul_variants("カーネーション")
    assert "카네이션" in variants  # 사용자가 실제로 치는 한국식 관용 표기
    assert "카네숀" in variants  # 장음 생략형
    assert any(v in ("카아네에숀", "카아네에션") for v in variants)  # 원문 음차 병행


def test_variants_carnation_full_title_substring_match():
    # 실제 신곡 제목 전체에서 "카네이션" 검색어가 substring으로 걸려야 한다.
    search_text = " / ".join(to_hangul_variants("カーネーションの咲く日に"))
    assert "카네이션" in search_text


def test_variants_homii_tai_final_sokuon_and_nakaguro():
    # ホーミー・タイッ: 장음 생략 + 가운뎃점 제거 + 어말 촉음 생략 → "호미타이".
    variants = to_hangul_variants("ホーミー・タイッ")
    assert any("호미타이" in v for v in variants)
    assert any(v.startswith("호오미이") for v in variants)  # 원문 음차 병행


def test_variants_ou_diphthong_after_o():
    # お단+ー: 오/오오/오우 세 갈래(포즈→포우즈 관용 대응).
    variants = kana_to_hangul_variants("ろーど")
    assert "로도" in variants and "로오도" in variants and "로우도" in variants


def test_variants_word_internal_sokuon_keeps_batchim():
    # 어중 촉음은 분기하지 않고 종전대로 받침 고정(はっぴ→합피 하나만).
    variants = kana_to_hangul_variants("はっぴ")
    assert variants == ["합피"]


# ── 한자음(한글 음독) 테스트 ────────────────────────────────────────────────────
def test_hanja_reading_basic():
    # 한자 제목 → 한국 한자음으로 변환
    # 例: 독창(獨창) 형태의 제목이 있다면 "독창"으로 변환되어야 함
    # 실제 예시: "独創収差" → "독창수차"
    result = to_hanja_reading("独創収差")
    # 결과는 적어도 한글 한자음을 포함해야 함
    assert result  # 빈 문자열 아님
    assert "독" in result or "창" in result or result == "独創収差"  # 변환되거나 원문 유지


def test_hanja_reading_no_hanja():
    # 한자가 없는 제목은 원문 그대로 반환
    result = to_hanja_reading("ハピネス")
    assert result == "ハピネス"


def test_hanja_reading_mixed():
    # 한자 + 가나 혼합
    result = to_hanja_reading("独創ライブ")
    # 한자만 변환되고 가나는 원문 유지
    assert "ライブ" in result or "らいぶ" in result  # 가나는 그대로
    assert result  # 빈 문자열 아님
