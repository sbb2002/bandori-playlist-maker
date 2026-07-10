"""하모닉 호환 판정 래퍼.

cross-team import(허용): `src/scripts/data/camelot.py`의 `is_adjacent()` — 표준 라이브러리
순수 함수이므로 도메인 순수성 위반이 아니다(architecture.md §② · backend/README §5).
이 모듈은 camelot.py를 편집하지 않고 읽기 전용으로 재사용한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# src/scripts/data 를 import 경로에 추가 (패키징 없이 cross-team 모듈 재사용).
#   harmonic.py: .../src/backend/app/domain/harmonic.py → parents[3] == .../src
_SCRIPTS_DATA = Path(__file__).resolve().parents[3] / "scripts" / "data"
if str(_SCRIPTS_DATA) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DATA))

from camelot import is_adjacent  # noqa: E402  (cross-team, 경로 삽입 후 import)


def is_compatible(prev_camelot: str, cur_camelot: str) -> bool:
    """직전 곡과 하모닉하게 이어지는지 여부.

    선곡 규칙(architecture.md §③ 스키마2 5): 동일 조성(`a == b`) 또는 인접
    (`is_adjacent`)이면 호환으로 본다.
    """
    return prev_camelot == cur_camelot or is_adjacent(prev_camelot, cur_camelot)


def harmonic_label(prev_camelot: str | None, cur_camelot: str) -> str:
    """직전 곡 대비 현재 곡의 하모닉 관계 라벨.

    Returns:
        "seed"        — 직전 곡 없음(첫 곡, 하모닉 제약 없음)
        "same"        — 동일 조성
        "adjacent"    — Camelot 인접
        "non_harmonic"— 비인접(인접 후보 소진 폴백; key 신뢰도 미검증 감안 — §④-4)
    """
    if prev_camelot is None:
        return "seed"
    if prev_camelot == cur_camelot:
        return "same"
    if is_adjacent(prev_camelot, cur_camelot):
        return "adjacent"
    return "non_harmonic"
