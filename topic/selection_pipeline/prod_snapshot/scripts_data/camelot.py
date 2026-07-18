"""key 표기 (예: ``Amaj``, ``F#min``) -> Camelot Wheel 코드 (1A~12B) 매핑.

입력 형식 (실측 확인, PRD §6 / 데이터팀 팀장 티켓3 명세 기준):
    - 정규식 ``^[A-G]#?(maj|min)$``
    - 샤프(#)만 사용, 플랫(b) 표기는 없음
    - 고유값 정확히 24종 (12 장조 + 12 단조)

표준 라이브러리만 사용한다.

Camelot Wheel 규칙:
    - 번호(1~12)는 5도권 순환, 문자는 조성(A=단조/minor, B=장조/major)을 나타낸다.
    - 하모닉 믹싱 인접 규칙: 같은 번호의 A<->B(관계조), 같은 문자에서 번호 ±1(순환,
      12<->1 포함)이 "인접"(자연스러운 전환)으로 간주된다.

표준 Camelot 매핑표 (샤프 표기, 이 프로젝트 입력 형식에 맞춤):

    Camelot | Major (B)  | Minor (A)
    --------|------------|------------
    1       | Bmaj       | G#min
    2       | F#maj      | D#min
    3       | C#maj      | A#min
    4       | G#maj      | Fmin
    5       | D#maj      | Cmin
    6       | A#maj      | Gmin
    7       | Fmaj       | Dmin
    8       | Cmaj       | Amin
    9       | Gmaj       | Emin
    10      | Dmaj       | Bmin
    11      | Amaj       | F#min
    12      | Emaj       | C#min
"""

from __future__ import annotations

import re

# key 문자열 유효성 검증용 정규식 (실측 기준: 샤프만, 플랫 없음).
_KEY_PATTERN = re.compile(r"^[A-G]#?(maj|min)$")

# key -> Camelot 코드 1:1 매핑 (24종 전수, 표준 Camelot Wheel 기준).
# 근거: 데이터팀 팀장 티켓3 명세 예시 전부 충족
#   Bmaj=1B, F#maj=2B, Amaj=11B, Emin=9A, Amin=8A, G#min=1A, D#min=2A
KEY_TO_CAMELOT: dict[str, str] = {
    # --- Major (B) ---
    "Bmaj": "1B",
    "F#maj": "2B",
    "C#maj": "3B",
    "G#maj": "4B",
    "D#maj": "5B",
    "A#maj": "6B",
    "Fmaj": "7B",
    "Cmaj": "8B",
    "Gmaj": "9B",
    "Dmaj": "10B",
    "Amaj": "11B",
    "Emaj": "12B",
    # --- Minor (A) ---
    "G#min": "1A",
    "D#min": "2A",
    "A#min": "3A",
    "Fmin": "4A",
    "Cmin": "5A",
    "Gmin": "6A",
    "Dmin": "7A",
    "Amin": "8A",
    "Emin": "9A",
    "Bmin": "10A",
    "F#min": "11A",
    "C#min": "12A",
}

# 역방향(Camelot -> key) 매핑. KEY_TO_CAMELOT이 24:24 1:1 전단사이므로 손실 없이 생성 가능.
CAMELOT_TO_KEY: dict[str, str] = {v: k for k, v in KEY_TO_CAMELOT.items()}

_CAMELOT_PATTERN = re.compile(r"^(1[0-2]|[1-9])([AB])$")


def to_camelot(key: str) -> str:
    """key 표기(예: ``Amaj``, ``F#min``)를 Camelot 코드(예: ``11B``, ``11A``)로 변환한다.

    Args:
        key: ``^[A-G]#?(maj|min)$`` 형식의 key 문자열 (샤프만 허용).

    Returns:
        Camelot 코드 문자열 (``"1A"``~``"12B"``).

    Raises:
        ValueError: key가 24종 매핑 테이블에 없는 경우 (형식 위반 포함, 예: 플랫 표기,
            알 수 없는 key 등).
    """
    try:
        return KEY_TO_CAMELOT[key]
    except KeyError:
        raise ValueError(f"알 수 없는 key 표기: {key!r} (허용 형식: ^[A-G]#?(maj|min)$, 24종 전수)") from None


def _validate_camelot(camelot: str) -> tuple[int, str]:
    """Camelot 코드 문자열을 (번호, 문자) 튜플로 파싱·검증한다."""
    match = _CAMELOT_PATTERN.match(camelot)
    if not match:
        raise ValueError(f"알 수 없는 Camelot 코드: {camelot!r} (허용 형식: 1~12 + A|B)")
    return int(match.group(1)), match.group(2)


def adjacent(camelot: str) -> set[str]:
    """하모닉 믹싱 인접 Camelot 코드 집합을 반환한다.

    인접 규칙(PRD §4-4):
        - 같은 번호의 A<->B 전환 (예: 8A -> 8B)
        - 같은 문자에서 번호 ±1, 12<->1 순환 포함 (예: 8A -> 7A, 9A / 12A -> 1A / 1A -> 12A)

    자기 자신은 포함하지 않는다(동일 코드는 "인접"이 아니라 "동일"이므로 제외).

    Args:
        camelot: Camelot 코드 문자열 (예: ``"8A"``).

    Returns:
        인접한 Camelot 코드 3개로 구성된 집합. 예: ``adjacent("8A") == {"8B", "7A", "9A"}``.

    Raises:
        ValueError: 유효하지 않은 Camelot 코드인 경우.
    """
    number, letter = _validate_camelot(camelot)
    other_letter = "A" if letter == "B" else "B"
    prev_number = 12 if number == 1 else number - 1
    next_number = 1 if number == 12 else number + 1
    return {
        f"{number}{other_letter}",
        f"{prev_number}{letter}",
        f"{next_number}{letter}",
    }


def is_adjacent(a: str, b: str) -> bool:
    """두 Camelot 코드가 하모닉 믹싱상 인접한지 여부를 반환한다.

    ``a == b``(동일 코드)는 인접으로 취급하지 않는다(``adjacent()``가 자기 자신을
    포함하지 않는 것과 일관됨). 동일 여부를 확인하려면 별도로 ``a == b``를 검사할 것.

    Args:
        a: Camelot 코드 문자열.
        b: Camelot 코드 문자열.

    Returns:
        b가 a의 인접 집합에 속하면 True.

    Raises:
        ValueError: a 또는 b가 유효하지 않은 Camelot 코드인 경우.
    """
    _validate_camelot(b)  # b도 유효한 코드인지 명시적으로 검증 (adjacent()는 a만 검증함)
    return b in adjacent(a)
