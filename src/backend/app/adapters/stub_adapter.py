"""스텁 어댑터 — LLM 없이 도는 결정적 휴리스틱 MoodInterpreter 구현.

목적: OpenRouter 키가 없는 상태에서도 전체 파이프라인(해석→선곡→API→프론트)을 끝까지 구동·
검증하기 위한 것(현재 마일스톤: '앱 구동 확인'). 키가 제공되면 main.py가 OpenRouter 어댑터로
교체하며, 이 파일은 도메인/선곡 로직과 무관하게 폐기·유지 가능하다.

주의: 이것은 진짜 자연어 이해가 아니라 키워드 기반 근사다. 운영 품질은 OpenRouter 어댑터가 담당.
"""

from __future__ import annotations

import re

from ..domain.models import MoodParameters
from .prompt import (
    DEFAULT_BRIGHTNESS,
    DEFAULT_STAGE_COUNT,
    DEFAULT_START_ENERGY,
)

# 키워드 → (brightness 가중, 시작 에너지 힌트, 종료 에너지 힌트).
_BRIGHT_WORDS = ("밝", "기분 좋", "신나", "행복", "설레", "상쾌", "경쾌", "bright", "happy", "cheer")
_DARK_WORDS = ("어두", "우울", "슬프", "슬픈", "차분", "잔잔", "쓸쓸", "몽환", "dark", "sad", "calm", "mellow")

_HIGH_ENERGY_WORDS = ("신나", "댄스", "파티", "운동", "질주", "축제", "열정", "고조", "party", "dance", "workout", "hype")
_LOW_ENERGY_WORDS = ("차분", "집중", "잔잔", "휴식", "수면", "명상", "공부", "잠들", "focus", "study", "sleep", "relax", "chill")

_RISE_WORDS = ("점점", "고조", "올라", "끌어올", "달아오", "build", "rise")
_FALL_WORDS = ("가라앉", "마무리", "식", "진정", "내려", "wind down", "cool down")

# 단위는 한국어 조사가 뒤에 붙을 수 있어(예: "30분만") 후행 \b를 쓰지 않는다.
# 오탐 위험이 있는 단문자 h/m 약어는 제외하고 명확한 단위만 인식한다.
_MINUTES_RE = re.compile(r"(\d+)\s*(시간|hours?|hrs?|분|minutes?|mins?)", re.IGNORECASE)


def _extract_minutes(text: str) -> int | None:
    """발화에서 재생시간(분)을 추출한다. '시간/hour'는 60배. 10~180으로 클램프."""
    match = _MINUTES_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith(("시간", "hour", "hr")):
        value *= 60
    return max(10, min(180, value))


def _count(text: str, words: tuple[str, ...]) -> int:
    return sum(1 for w in words if w.lower() in text)


class StubMoodInterpreter:
    """키워드 휴리스틱 기반 MoodInterpreter(오프라인·결정적)."""

    def interpret(self, prompt: str) -> MoodParameters:
        text = prompt.lower()

        # 밝기: 밝음/어두움 키워드 카운트 차이를 -1~1로 스케일.
        bright_hits = _count(text, _BRIGHT_WORDS)
        dark_hits = _count(text, _DARK_WORDS)
        if bright_hits or dark_hits:
            brightness = max(-1.0, min(1.0, 0.5 * (bright_hits - dark_hits)))
        else:
            brightness = DEFAULT_BRIGHTNESS

        # 에너지: high/low 키워드로 시작 에너지 기준점 결정.
        high_hits = _count(text, _HIGH_ENERGY_WORDS)
        low_hits = _count(text, _LOW_ENERGY_WORDS)
        if high_hits > low_hits:
            start_energy = 0.55
        elif low_hits > high_hits:
            start_energy = 0.25
        else:
            start_energy = DEFAULT_START_ENERGY

        # 진행 방향: 명시 키워드 우선, 없으면 밝은 요청은 소폭 상승 기본.
        if _count(text, _RISE_WORDS):
            end_energy = min(1.0, start_energy + 0.4)
        elif _count(text, _FALL_WORDS):
            end_energy = max(0.0, start_energy - 0.3)
        elif brightness > 0:
            end_energy = min(1.0, start_energy + 0.25)
        else:
            end_energy = start_energy

        target_minutes = _extract_minutes(text)

        summary, tags = _flavor(brightness, start_energy, end_energy, target_minutes)

        return MoodParameters(
            brightness=round(brightness, 3),
            start_energy=round(start_energy, 3),
            end_energy=round(end_energy, 3),
            stage_count=DEFAULT_STAGE_COUNT,
            target_minutes=target_minutes,
            interpretation_summary=summary,
            tags=tags,
        )


def _flavor(brightness, start_energy, end_energy, target_minutes):
    """수치 대신 감성 플레이버 텍스트 + 해시태그를 휴리스틱으로 만든다(스텁 품질)."""
    mood = "밝고 경쾌한" if brightness > 0.3 else "차분하고 잔잔한" if brightness < -0.3 else "은은한"
    diff = end_energy - start_energy
    arc = "점점 달아오르는" if diff > 0.1 else "서서히 가라앉는" if diff < -0.1 else "한결같은 흐름의"
    mins = f" 약 {target_minutes}분" if target_minutes else ""
    summary = f"{mood} {arc}{mins} 세트리스트"

    tags: list[str] = []
    if brightness > 0.3:
        tags.append("밝은")
    elif brightness < -0.3:
        tags.append("울적한")
    if start_energy >= 0.55:
        tags.append("신나는")
    elif start_energy <= 0.3:
        tags.append("잔잔한")
    if diff > 0.1:
        tags.append("고조되는")
    elif diff < -0.1:
        tags.append("잔잔해지는")
    return summary, (tags[:5] or None)
