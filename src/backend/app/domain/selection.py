"""선곡 엔진 — `build_setlist()` 순수·결정적 함수 (진입점).

architecture.md §③ 스키마2 알고리즘 구현. LLM 출력(MoodParameters)만 입력받으며
외부 서비스에 의존하지 않는다. 동일 입력 → 동일 출력(결정적).
"""

from __future__ import annotations

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


def _sort_key(
    song: Song,
    energy_target: float,
    brightness_target: float,
    brightness: dict[int, float],
    prev: Song | None,
) -> tuple[float, float, int, int]:
    """후보 정렬 키(작을수록 우선). 밴드 연속 억제는 동점 타이브레이크로만 작용(§③ 스키마2 6)."""
    energy_dist = abs(song.energy - energy_target)
    brightness_dist = abs(brightness[song.idx] - brightness_target)
    same_band_penalty = 1 if (prev is not None and song.band == prev.band) else 0
    return (round(energy_dist, 6), round(brightness_dist, 6), same_band_penalty, song.idx)


def _choose(
    remaining: dict[int, Song],
    energy_target: float,
    brightness_target: float,
    brightness: dict[int, float],
    prev: Song | None,
) -> Song:
    """단계 내 다음 곡 1개 선택: 하모닉 호환 후보 우선, 소진 시 non_harmonic 폴백."""
    candidates = list(remaining.values())
    if prev is not None:
        compatible = [c for c in candidates if is_compatible(prev.camelot, c.camelot)]
        pool = compatible if compatible else candidates
    else:
        pool = candidates  # 첫 곡(seed) — 하모닉 제약 없음
    return min(pool, key=lambda c: _sort_key(c, energy_target, brightness_target, brightness, prev))


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
) -> Setlist:
    """무드/에너지 파라미터로 세트리스트를 구성한다(순수·결정적).

    Args:
        songs: 전체 곡 목록(repo 로더 산출). `eligible_band == True`만 후보로 쓴다.
        params: LLM 해석 결과(검증 완료).
        target_seconds: 목표 총 재생시간(초).
        avg_song_seconds: duration 부재 시 곡 길이 추정치(초).
        band_filter: 밴드 화이트리스트(§5-1b 확장 예약, 기본 None=ALL).

    Returns:
        Setlist(단계·추정시간·곡 순서·선곡 이유 포함).

    Raises:
        NoSetlistError: 후보곡이 0건이라 세트리스트를 만들 수 없는 경우.
    """
    pool = [s for s in songs if s.eligible_band]
    if band_filter:
        pool = [s for s in pool if s.band in band_filter]
    if not pool:
        raise NoSetlistError("후보곡이 없습니다(eligible_band/band_filter 결과 0건).")

    brightness = _brightness_scores(pool)
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
            picked = _choose(remaining, energy_target, params.brightness, brightness, prev)
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
