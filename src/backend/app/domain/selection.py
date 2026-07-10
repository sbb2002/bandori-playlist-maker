"""선곡 엔진 — `build_setlist()` 순수·결정적 함수 (진입점).

architecture.md §③ 스키마2 알고리즘 구현. LLM 출력(MoodParameters)만 입력받으며
외부 서비스에 의존하지 않는다. 동일 입력 → 동일 출력(결정적).
"""

from __future__ import annotations

import math
import random

from .energy import distribute_counts, stage_energy_targets, total_song_count
from .harmonic import harmonic_label, is_compatible
from .models import (
    MoodParameters,
    NoSetlistError,
    Pick,
    PickReason,
    Setlist,
    Song,
    Stage,
    StageSpec,
)

# shape(음색 시그니처) → 밝기 보조 가중(architecture.md §③ 스키마2 2: mode_score 주 신호 + shape 보조).
_SHAPE_BRIGHTNESS: dict[str, float] = {
    "bright": 0.15,
    "shimmer": 0.10,
    "neutral": 0.0,
    "acoustic": -0.10,
}

# duration 데이터 부재 시 곡 길이 플레이스홀더(architecture.md §④-2, 초 단위).
DEFAULT_AVG_SONG_SECONDS = 213


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _brightness_scores(pool: list[Song]) -> dict[int, float]:
    """곡별 밝기 점수(-1~1). mode_score min-max 정규화(주) + shape 보조 가중."""
    mode_scores = [s.mode_score for s in pool]
    lo, hi = min(mode_scores), max(mode_scores)
    span = hi - lo
    scores: dict[int, float] = {}
    for s in pool:
        norm = (s.mode_score - lo) / span if span > 0 else 0.5
        base = norm * 2.0 - 1.0
        adjusted = base + _SHAPE_BRIGHTNESS.get(s.shape, 0.0)
        scores[s.idx] = _clamp(adjusted, -1.0, 1.0)
    return scores


# 확률적 선곡 가중치 파라미터(요구 부합도 → 확률). 작을수록 뾰족(부합곡 집중), 클수록 다양성↑.
_ENERGY_SIGMA = 0.15   # 에너지 부합 민감도(0~1 축)
_BRIGHTNESS_SIGMA = 0.5  # 밝기 부합 민감도(-1~1 축, 상대적으로 완만)
_HARMONIC_BONUS = 4.0  # 직전 곡과 하모닉 호환 시 가중 배수(하드 필터 아님 — key 신뢰도 미검증)
_SAME_BAND_FACTOR = 0.5  # 직전 곡과 같은 밴드면 가중 감쇠(연속 억제)
_MAX_PICK_PROB = 0.30  # 단일 곡 최대 선택 확률 상한(한 곡 독점 방지 — 좁은 후보군 대비)


def _weight(
    song: Song,
    energy_target: float,
    brightness_target: float,
    brightness: dict[int, float],
    prev: Song | None,
) -> float:
    """후보 곡의 선택 가중치(클수록 요구에 부합 → 높은 확률). 가우시안 부합도 곱."""
    energy_dist = abs(song.energy - energy_target)
    brightness_dist = abs(brightness[song.idx] - brightness_target)
    weight = math.exp(-((energy_dist / _ENERGY_SIGMA) ** 2))
    weight *= math.exp(-((brightness_dist / _BRIGHTNESS_SIGMA) ** 2))
    if prev is not None:
        weight *= _HARMONIC_BONUS if is_compatible(prev.camelot, song.camelot) else 1.0
        if song.band == prev.band:
            weight *= _SAME_BAND_FACTOR
    return weight


def _cap_probabilities(probs: list[float], cap: float) -> list[float]:
    """단일 확률이 cap을 넘지 않도록 초과분을 여유 있는 후보에 재분배한다.

    후보 수가 적어 cap이 물리적으로 불가능하면(1/n > cap) 실현 가능한 하한(1/n)으로 완화한다.
    """
    n = len(probs)
    if n == 0:
        return probs
    cap = max(cap, 1.0 / n)
    probs = list(probs)
    for _ in range(50):
        total = sum(probs)
        if total <= 0.0:
            return [1.0 / n] * n
        probs = [p / total for p in probs]
        over = [i for i, p in enumerate(probs) if p > cap + 1e-12]
        if not over:
            break
        excess = sum(probs[i] - cap for i in over)
        for i in over:
            probs[i] = cap
        room = [(i, cap - probs[i]) for i in range(n) if probs[i] < cap - 1e-12]
        room_total = sum(r for _, r in room)
        if room_total <= 1e-12:
            break
        for i, r in room:
            probs[i] += excess * (r / room_total)
    return probs


def _choose(
    remaining: dict[int, Song],
    energy_target: float,
    brightness_target: float,
    brightness: dict[int, float],
    prev: Song | None,
    rng: random.Random,
) -> Song:
    """단계 내 다음 곡 1개를 부합도 가중 확률로 샘플링한다(요구 부합↑ → 확률↑, 상한 제한).

    하모닉은 하드 필터가 아니라 가중치(×4)로 반영 — 다양성을 유지하면서 흐름을 선호.
    단일 곡 독점을 막기 위해 확률 상한(`_MAX_PICK_PROB`)을 적용한다.
    가중치 합이 0이면 에너지 근접 결정적 폴백.
    """
    candidates = list(remaining.values())  # dict 삽입순 = 결정적 순서(시드 재현성)
    weights = [_weight(c, energy_target, brightness_target, brightness, prev) for c in candidates]
    total = sum(weights)
    if total <= 0.0:
        return min(candidates, key=lambda c: (abs(c.energy - energy_target), c.idx))
    probs = _cap_probabilities([w / total for w in weights], _MAX_PICK_PROB)
    threshold = rng.random()
    acc = 0.0
    for candidate, prob in zip(candidates, probs):
        acc += prob
        if threshold <= acc:
            return candidate
    return candidates[-1]


def _make_reason(
    energy_target: float,
    picked: Song,
    picked_brightness: float,
    brightness_target: float,
    prev: Song | None,
    harmonic: str,
    stage_index: int,
) -> PickReason:
    brightness_fit = round(1.0 - abs(picked_brightness - brightness_target) / 2.0, 3)
    if harmonic == "seed":
        harmonic_text = "시작 곡 — 하모닉 제약 없음."
    elif harmonic == "same":
        harmonic_text = f"직전 곡과 동일 조성({picked.camelot})."
    elif harmonic == "adjacent":
        harmonic_text = f"직전 곡과 하모닉 인접({prev.camelot}→{picked.camelot})."  # type: ignore[union-attr]
    else:  # non_harmonic
        harmonic_text = f"인접 후보 소진 — 조성 전환({prev.camelot}→{picked.camelot})."  # type: ignore[union-attr]
    text = (
        f"{stage_index + 1}단계 에너지 목표 {energy_target:.2f}에 근접"
        f"(곡 에너지 {picked.energy:.2f}). {harmonic_text}"
    )
    return PickReason(
        stage_energy_target=round(energy_target, 4),
        matched_energy=round(picked.energy, 4),
        harmonic=harmonic,
        prev_camelot=(prev.camelot if prev is not None else None),
        brightness_fit=brightness_fit,
        text=text,
    )


def build_setlist(
    songs: list[Song],
    params: MoodParameters,
    target_seconds: int,
    avg_song_seconds: int = DEFAULT_AVG_SONG_SECONDS,
    band_filter: set[str] | None = None,
    stage_specs: list[StageSpec] | None = None,
    rng: random.Random | None = None,
) -> Setlist:
    """무드/에너지 파라미터로 세트리스트를 구성한다(부합도 가중 확률적 선곡).

    Args:
        songs: 전체 곡 목록(repo 로더 산출). `eligible_band == True`만 후보로 쓴다.
        params: LLM 해석 결과(검증 완료).
        target_seconds: 목표 총 재생시간(초).
        avg_song_seconds: duration 부재 시 곡 길이 추정치(초).
        band_filter: 밴드 화이트리스트(설정 기능 §5-1b, 기본 None=ALL).
        stage_specs: 사용자 지정 단계 스펙(설정 기능 §5-1a). 주어지면 에너지 아크·곡 수를
            이 값으로 강제하고 LLM 유도 산정을 건너뛴다.
        rng: 선곡 샘플링 RNG. None이면 매 호출 새 시드(운영: 매번 다른 결과). 동일 시드를
            주면 결정적 재현(테스트).

    Returns:
        Setlist(단계·추정시간·곡 순서·선곡 이유 포함).

    Raises:
        NoSetlistError: 후보곡이 0건이라 세트리스트를 만들 수 없는 경우.
    """
    if rng is None:
        rng = random.Random()
    pool = [s for s in songs if s.eligible_band]
    if band_filter:
        pool = [s for s in pool if s.band in band_filter]
    if not pool:
        raise NoSetlistError("후보곡이 없습니다(eligible_band/band_filter 결과 0건).")

    brightness = _brightness_scores(pool)
    if stage_specs:
        # 사용자 지정 단계: 에너지·곡 수를 그대로 사용(0~1 클램프만).
        targets = [_clamp(s.energy_target, 0.0, 1.0) for s in stage_specs]
        counts = [max(1, s.song_count) for s in stage_specs]
    else:
        targets = stage_energy_targets(params.start_energy, params.end_energy, params.stage_count)
        total = min(total_song_count(target_seconds, avg_song_seconds, params.stage_count), len(pool))
        counts = distribute_counts(total, params.stage_count)

    remaining = {s.idx: s for s in pool}
    stages_out: list[Stage] = []
    picks: list[Pick] = []
    prev: Song | None = None
    position = 0

    for stage_index, (energy_target, count) in enumerate(zip(targets, counts)):
        stages_out.append(Stage(index=stage_index, energy_target=round(energy_target, 4)))
        for _ in range(count):
            if not remaining:
                break
            picked = _choose(remaining, energy_target, params.brightness, brightness, prev, rng)
            harmonic = harmonic_label(None if prev is None else prev.camelot, picked.camelot)
            reason = _make_reason(
                energy_target, picked, brightness[picked.idx], params.brightness,
                prev, harmonic, stage_index,
            )
            picks.append(
                Pick(
                    position=position,
                    idx=picked.idx,
                    video_id=picked.video_id,
                    band=picked.band,
                    song=picked.song,
                    camelot=picked.camelot,
                    energy=picked.energy,
                    stage_index=stage_index,
                    reason=reason,
                )
            )
            del remaining[picked.idx]
            prev = picked
            position += 1

    if not picks:
        raise NoSetlistError("세트리스트를 구성하지 못했습니다(곡 수 산정 결과 0).")

    by_idx = {s.idx: s for s in pool}
    estimated_total_seconds = sum(
        (by_idx[p.idx].duration_sec or avg_song_seconds) for p in picks
    )
    return Setlist(
        params=params,
        stages=stages_out,
        estimated_total_seconds=estimated_total_seconds,
        picks=picks,
    )
