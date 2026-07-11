"""프롬프트의 밴드명(별명 포함) → 밴드 필터 자동 감지.

사용자 요청(2026-07-11): "RAS와 뮤타입 노래로 …" 처럼 밴드명을 명시하면 해당 밴드만 자동
선택. 별명 매핑은 사용자 제공. 결정적(부분 문자열) 매칭이라 LLM 무의존.
"""

from __future__ import annotations

# 정규 밴드명(= songs_master.csv의 band 값) → 별명 목록(소문자 비교).
BAND_ALIASES: dict[str, tuple[str, ...]] = {
    "poppin_party": ("poppin_party", "poppin party", "popipa", "포핀파티", "포피파", "뽀삐빠"),
    "roselia": ("roselia", "로젤리아", "로젤", "로제리아", "로제"),
    "raise_a_suilen": ("raise_a_suilen", "raise a suilen", "ras", "라스", "레이즈어수이렌", "레이즈 어 수이렌"),
    "pastel_palettes": ("pastel_palettes", "pastel palettes", "pastel", "파스텔팔레트", "파스텔 팔레트", "파스파레", "파스텔"),
    "afterglow": ("afterglow", "애프터글로우", "앱글"),
    "hello_happy_world": ("hello_happy_world", "hello happy world", "hello happy", "헬로해피월드", "헬로해피", "하로하피", "하로핫삐", "하로하삐"),
    "morfonica": ("morfonica", "모르포니카", "몰포니카", "몰포"),
    "mygo": ("mygo", "마이고", "미아"),
    "ave_mujica": ("ave_mujica", "ave mujica", "아베무지카", "아베무", "아베"),
    "mugendai_mutype": ("mugendai_mutype", "mugendai mutype", "mutype", "뮤타입", "믂타입", "무겐다이 뮤타입", "유메미타", "윾메미타"),
}


def detect_bands(prompt: str) -> set[str]:
    """프롬프트에서 언급된 밴드(정규명) 집합을 반환한다(없으면 빈 집합).

    소문자 부분 문자열 매칭. 짧은 별명(예: '로제', '아베', '미아')은 오탐 여지가 있으나
    음악 무드 요청 맥락에서는 의도적 언급으로 간주한다(사용자 설계).
    """
    text = prompt.lower()
    found: set[str] = set()
    for band, aliases in BAND_ALIASES.items():
        if any(alias in text for alias in aliases):
            found.add(band)
    return found
