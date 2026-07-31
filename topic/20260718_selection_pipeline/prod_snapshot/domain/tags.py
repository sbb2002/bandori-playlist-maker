"""요약 카드용 해시태그 파생 — 무드 파라미터 기반 순수 함수.

외부 의존 없음(architecture.md §③ 도메인 규칙). LLM이 tags를 비우거나 1개만 줘도
Summary Card가 허전하지 않도록, 이미 산출된 무드 파라미터에서 요약을 대표하는
대표 키워드를 결정론적으로 파생해 **최소 2개~최대 5개**를 보장한다.

파라미터는 interpretation_summary와 같은 근거에서 나오므로, 여기서 만든 태그는
자연스럽게 요약 문구의 분위기를 대표한다.
"""

from __future__ import annotations

MIN_TAGS = 2
MAX_TAGS = 5


def derive_tags(
    brightness: float,
    start_energy: float,
    end_energy: float,
    target_minutes: int | None = None,
) -> list[str]:
    """무드 파라미터에서 요약을 대표하는 후보 키워드를 우선순위 순으로 만든다.

    밝기·에너지 두 축은 중립 구간에도 어휘를 부여하고 축 간 어휘가 겹치지 않게 하여,
    가장 밋밋한 요청(모든 축 중립)에서도 후보가 최소 3개는 나오도록 설계했다.
    """
    tags: list[str] = []

    # 밝기 축(항상 1~2개): interpretation_summary의 mood 형용사와 톤을 맞춘다.
    if brightness > 0.3:
        tags += ["밝은", "경쾌한"]
    elif brightness < -0.3:
        tags += ["감성", "잔잔한"]
    else:
        tags += ["은은한", "무드"]

    # 에너지 축(항상 1~2개): 밝기 축과 어휘가 겹치지 않게 고른다.
    if start_energy >= 0.55:
        tags += ["신나는", "활기찬"]
    elif start_energy <= 0.3:
        tags += ["차분한", "힐링"]
    else:
        tags += ["편안한"]

    # 진행 아크(있을 때만): 상승/하강 흐름을 키워드로.
    diff = end_energy - start_energy
    if diff > 0.1:
        tags.append("고조되는")
    elif diff < -0.1:
        tags.append("여운")

    # 재생 길이 힌트(길 때만): 롱플레이 감성 키워드.
    if target_minutes is not None and target_minutes >= 90:
        tags.append("롱플레이")

    return tags


def ensure_min_tags(
    existing: list[str] | None,
    brightness: float,
    start_energy: float,
    end_energy: float,
    target_minutes: int | None = None,
    *,
    minimum: int = MIN_TAGS,
    maximum: int = MAX_TAGS,
) -> list[str]:
    """기존 태그를 존중하되, minimum 미만이면 파생 키워드로 보충하고 maximum으로 캡한다.

    - existing이 이미 minimum개 이상이면 (중복 제거 후) 그대로 유지한다(LLM 결과 존중).
    - 부족하면 derive_tags 결과에서 중복 없이 minimum개가 될 때까지만 채운다.
    - 대소문자 무시로 중복을 제거하며 입력 순서를 보존한다.
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        clean = tag.strip().lstrip("#").strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            out.append(clean)

    for tag in existing or []:
        if isinstance(tag, str):
            add(tag)

    if len(out) < minimum:
        for tag in derive_tags(brightness, start_energy, end_energy, target_minutes):
            if len(out) >= minimum:
                break
            add(tag)

    return out[:maximum]
