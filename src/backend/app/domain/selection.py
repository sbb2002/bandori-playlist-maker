"""선곡 엔진 — `build_setlist()` 순수·결정적 함수 (진입점).

2단계 설계(R&D 보고서 docs/research/2026-07-11-playlist-sequencing-strategy.md §2):
- **Stage A — SELECT**: 각 단계 강도(intensity) 목표에 부합하는 곡을 하드하게 선택(무드 누출 차단).
- **Stage B — SEQUENCE**: 이미 무드가 맞는 곡을 가중 특징공간에서 HAM-2로 정렬(전환 매끄러움).

두 목표를 서로 다른 단계에서 각각 보장하므로 충돌하지 않는다. LLM 출력(MoodParameters)만
입력받으며 외부 서비스에 의존하지 않는다. 시드 고정 시 동일 입력 → 동일 출력(결정적).
`Song.energy`는 강도(intensity, 0~1) — song_repo가 percentile+power-mean으로 산출.
"""

from __future__ import annotations

import math
import random

from .energy import distribute_counts, stage_energy_targets, total_song_count
from .harmonic import harmonic_label
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

# 2단계 엔진 파라미터(R&D §4.2 권장 기본값). 파일럿 후 실사용 피드백으로 튜닝.
_TOL = 0.08              # Stage A 강도 허용창(목표에서 이 이내만 후보)
_BRIGHTNESS_BUCKET = 0.25  # Stage A 밝기 근접 버킷 폭(같은 버킷 내에선 rng 변주)
_W_E, _W_B, _W_T = 1.0, 0.9, 1.1  # 시퀀싱 특징 가중(에너지·밝기·조성)
_TONALITY_HEIGHT = 2.0 * math.sin(math.pi / 12)  # ≈0.5176, EPJ 조성 3D 임베딩 높이


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


def _tonality_xyz(camelot: str) -> tuple[float, float, float]:
    """Camelot 코드 → 5도권 12각기둥 3D 좌표(EPJ §4.6). 장조=바닥, 단조=높이 h."""
    number = int(camelot[:-1])
    letter = camelot[-1]
    theta = 2.0 * math.pi * (number - 1) / 12.0
    z = 0.0 if letter == "B" else _TONALITY_HEIGHT
    return (math.cos(theta), math.sin(theta), z)


def _feature(song: Song, brightness: dict[int, float]) -> tuple[float, ...]:
    """시퀀싱용 가중 특징벡터(에너지·밝기·조성3D)."""
    x, y, z = _tonality_xyz(song.camelot)
    brightness01 = brightness[song.idx] * 0.5 + 0.5
    return (_W_E * song.energy, _W_B * brightness01, _W_T * x, _W_T * y, _W_T * z)


def _distance(a: Song, b: Song, brightness: dict[int, float]) -> float:
    fa = _feature(a, brightness)
    fb = _feature(b, brightness)
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(fa, fb)))


def _sequence_ham2(members: list[Song], target: float, brightness: dict[int, float]) -> list[Song]:
    """HAM-2(Spotify §3.1.2): 시드에서 시작해 매 스텝 부분경로 머리/꼬리 중 특징거리 최소 곡 부착.

    시드 = 단계 강도 목표에 가장 가까운 곡. 결정적(members 순서·idx 타이브레이크).
    """
    seed = min(members, key=lambda s: (abs(s.energy - target), s.idx))
    seq = [seed]
    rem = [s for s in members if s.idx != seed.idx]
    while rem:
        head, tail = seq[0], seq[-1]
        best: Song | None = None
        best_dist = math.inf
        attach = "tail"
        for candidate in rem:
            dist_head = _distance(head, candidate, brightness)
            dist_tail = _distance(tail, candidate, brightness)
            if dist_head < best_dist:
                best_dist, best, attach = dist_head, candidate, "head"
            if dist_tail < best_dist:
                best_dist, best, attach = dist_tail, candidate, "tail"
        if attach == "head":
            seq.insert(0, best)  # type: ignore[arg-type]
        else:
            seq.append(best)  # type: ignore[arg-type]
        rem = [s for s in rem if s.idx != best.idx]  # type: ignore[union-attr]
    return seq


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
        harmonic_text = f"조성 전환({prev.camelot}→{picked.camelot})."  # type: ignore[union-attr]
    text = (
        f"{stage_index + 1}단계 강도 목표 {energy_target:.2f}에 부합"
        f"(곡 강도 {picked.energy:.2f}). {harmonic_text}"
    )
    return PickReason(
        stage_energy_target=round(energy_target, 4),
        matched_energy=round(picked.energy, 4),
        harmonic=harmonic,
        prev_camelot=(prev.camelot if prev is not None else None),
        brightness_fit=brightness_fit,
        text=text,
    )


def _stage_targets_and_counts(
    params: MoodParameters,
    target_seconds: int,
    avg_song_seconds: int,
    pool_size: int,
    stage_specs: list[StageSpec] | None,
) -> tuple[list[float], list[int]]:
    if stage_specs:
        targets = [_clamp(s.energy_target, 0.0, 1.0) for s in stage_specs]
        counts = [max(1, s.song_count) for s in stage_specs]
        return targets, counts
    targets = stage_energy_targets(params.start_energy, params.end_energy, params.stage_count)
    total = min(total_song_count(target_seconds, avg_song_seconds, params.stage_count), pool_size)
    counts = distribute_counts(total, params.stage_count)
    return targets, counts


def build_setlist(
    songs: list[Song],
    params: MoodParameters,
    target_seconds: int,
    avg_song_seconds: int = DEFAULT_AVG_SONG_SECONDS,
    band_filter: set[str] | None = None,
    stage_specs: list[StageSpec] | None = None,
    rng: random.Random | None = None,
) -> Setlist:
    """무드/에너지 파라미터로 세트리스트를 구성한다(2단계 SELECT→SEQUENCE).

    Args:
        songs: 전체 곡 목록(repo 로더 산출). `eligible_band == True`만 후보로 쓴다.
        params: LLM 해석 결과(검증 완료).
        target_seconds: 목표 총 재생시간(초).
        avg_song_seconds: duration 부재 시 곡 길이 추정치(초).
        band_filter: 밴드 화이트리스트(설정 기능 §5-1b, 기본 None=ALL).
        stage_specs: 사용자 지정 단계 스펙(설정 기능 §5-1a).
        rng: Stage A 후보 셔플 RNG. None이면 매 호출 새 시드(운영: 변주). 동일 시드 → 재현.

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
    targets, counts = _stage_targets_and_counts(
        params, target_seconds, avg_song_seconds, len(pool), stage_specs
    )

    # ── Stage A: SELECT — 단계별 강도 목표에 부합하는 곡을 하드 선택(누출 차단) ──
    remaining = {s.idx: s for s in pool}
    stage_members: list[list[Song]] = []
    for target, count in zip(targets, counts):
        if not remaining:
            stage_members.append([])
            continue
        cand = sorted(remaining.values(), key=lambda s: (abs(s.energy - target), s.idx))
        window = [s for s in cand if abs(s.energy - target) <= _TOL]
        if len(window) >= count:
            # 허용창 내 곡은 모두 무드 부합 → rng 셔플로 변주 후 밝기 버킷 근접 우선(재현적).
            rng.shuffle(window)
            window.sort(key=lambda s: round(abs(brightness[s.idx] - params.brightness) / _BRIGHTNESS_BUCKET))
            chosen = window[:count]
        else:
            chosen = cand[:count]  # 후보 부족 → 강도 근접 우선(변주 없음)
        for s in chosen:
            del remaining[s.idx]
        stage_members.append(chosen)

    # ── Stage B: SEQUENCE — 단계 내부 HAM-2 정렬 + 단계 경계 아크 접합 ──
    stages_out: list[Stage] = []
    picks: list[Pick] = []
    prev: Song | None = None
    position = 0
    ordered: list[Song] = []

    for stage_index, (target, members) in enumerate(zip(targets, stage_members)):
        stages_out.append(Stage(index=stage_index, energy_target=round(target, 4)))
        if not members:
            continue
        seq = _sequence_ham2(members, target, brightness)
        # 아크 접합: 이전 단계 끝 곡과 더 가까운 방향으로 이어붙인다(진행 아크 보존).
        if ordered and _distance(ordered[-1], seq[0], brightness) > _distance(ordered[-1], seq[-1], brightness):
            seq.reverse()
        for s in seq:
            harmonic = harmonic_label(None if prev is None else prev.camelot, s.camelot)
            reason = _make_reason(
                target, s, brightness[s.idx], params.brightness, prev, harmonic, stage_index
            )
            picks.append(
                Pick(
                    position=position,
                    idx=s.idx,
                    video_id=s.video_id,
                    band=s.band,
                    song=s.song,
                    camelot=s.camelot,
                    energy=s.energy,
                    stage_index=stage_index,
                    reason=reason,
                )
            )
            prev = s
            position += 1
        ordered.extend(seq)

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
