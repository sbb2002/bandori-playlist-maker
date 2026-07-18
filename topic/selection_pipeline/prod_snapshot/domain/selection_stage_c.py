"""선곡 엔진 — `build_setlist_with_stage_c()` 순수·결정적 함수 (진입점, DESIGN_v3.md Method 2 포크).

2단계 설계(R&D 보고서 document-archive 브랜치 archive/last-papers/research/2026-07-11-playlist-sequencing-strategy.md §2):
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

# 2단계 엔진 파라미터(R&D §4.2 권장 기본값). 파일럿 후 실사용 피드백으로 튜닝.
_TOL = 0.08              # Stage A 강도 허용창(목표에서 이 이내만 후보)
_BRIGHTNESS_BUCKET = 0.25  # Stage A 밝기 근접 버킷 폭(같은 버킷 내에선 rng 변주)
# Stage B 시퀀싱: 경계갭 + 하모닉을 다목적 비용으로 최소화. (검증 하네스로 튜닝 — R&D §8.)
_RANDOM_SLACK = 0.05     # 최소 비용 대비 이 범위 내 후보는 랜덤(곡 선택 변주는 Stage A가 담당)
_HARMONIC_PENALTY = 0.15  # 비하모닉 전환 비용(경계갭과 동일 단위; 경계 최소화와 하모닉 균형점)


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


def _sequence_by_continuity(
    members: list[Song],
    target: float,
    prev_outro: float | None,
    rng: random.Random,
) -> list[Song]:
    """곡 경계 텐션 연속성 기반 방향성 그리디 체인(사용자 §종합, 2026-07-11).

    이전 곡 **아웃트로 텐션 ↔ 다음 곡 인트로 텐션**의 차이를 최소화하도록 이어붙인다. 곡 *내부*
    텐션 변동은 정상으로 보고 무시하며, 오직 곡 *경계*의 급차이만 줄인다.

    - seed: 이전 스테이지 아웃트로가 있으면 그와 인트로가 가장 가까운 곡(경계 접합), 없으면(첫
      스테이지) 단계 강도 목표 근접 곡.
    - 이후: 직전 곡 아웃트로와 인트로 차가 최소인 후보(±`_CONT_WINDOW`) 중, 하모닉 호환을
      소프트 우선하고 그 안에서 랜덤 선택(사용자 '랜덤 셀렉트' + 다양성).
    """
    if prev_outro is None:
        # 오프너(전체 첫 곡): 강도 부합 후보 중 **인트로 텐션이 가장 높은** 곡으로 시드한다
        # (에너지 있는 시작 — 파티/운동 요청의 조용한 인트로 오프너 문제 해소, R&D §8-3).
        by_fit = sorted(members, key=lambda s: (abs(s.energy - target), s.idx))
        fit_window = [s for s in by_fit if abs(s.energy - target) <= _TOL] or by_fit[:5]
        seed = max(fit_window, key=lambda s: (s.intro_energy, -s.idx))
    else:
        # 스테이지 경계 접합: 이전 스테이지 아웃트로와 인트로가 가장 가까운 곡.
        seed = min(members, key=lambda s: (abs(prev_outro - s.intro_energy), s.idx))
    seq = [seed]
    rem = [s for s in members if s.idx != seed.idx]
    while rem:
        current = seq[-1]

        def cost(candidate: Song, cur: Song = current) -> float:
            gap = abs(cur.outro_energy - candidate.intro_energy)
            penalty = 0.0 if is_compatible(cur.camelot, candidate.camelot) else _HARMONIC_PENALTY
            return gap + penalty

        rem.sort(key=lambda c: (cost(c), c.idx))
        best = cost(rem[0])
        window = [c for c in rem if cost(c) <= best + _RANDOM_SLACK]
        pick = rng.choice(window)
        seq.append(pick)
        rem.remove(pick)
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
    if params.stage_energies:
        # 비단조 아크(LLM 산출): 단계별 에너지 배열을 그대로 목표로. 곡 수는 균등 분배.
        targets = [_clamp(e, 0.0, 1.0) for e in params.stage_energies]
        n = len(targets)
        total = min(total_song_count(target_seconds, avg_song_seconds, n), pool_size)
        return targets, distribute_counts(total, n)
    targets = stage_energy_targets(params.start_energy, params.end_energy, params.stage_count)
    total = min(total_song_count(target_seconds, avg_song_seconds, params.stage_count), pool_size)
    counts = distribute_counts(total, params.stage_count)
    return targets, counts


def build_setlist_with_stage_c(
    songs: list[Song],
    params: MoodParameters,
    target_seconds: int,
    avg_song_seconds: int = DEFAULT_AVG_SONG_SECONDS,
    band_filter: set[str] | None = None,
    stage_specs: list[StageSpec] | None = None,
    rng: random.Random | None = None,
    lyric_scores: dict[int, float] | None = None,
) -> Setlist:
    """무드/에너지 파라미터로 세트리스트를 구성한다(3단계 STAGE C→SELECT→SEQUENCE).

    DESIGN_v3.md §0/§1: 원본 `build_setlist()`에 Stage C(가사 후보추림)를 Stage A 직전에
    삽입한 포크. Stage A·B·파라미터 분기 등 나머지 로직은 원본과 1바이트도 다르지 않다
    (diff 검증 대상 — DESIGN_v3.md §1).

    Args:
        songs: 전체 곡 목록(repo 로더 산출). `eligible_band == True`만 후보로 쓴다.
        params: LLM 해석 결과(검증 완료).
        target_seconds: 목표 총 재생시간(초).
        avg_song_seconds: duration 부재 시 곡 길이 추정치(초).
        band_filter: 밴드 화이트리스트(설정 기능 §5-1b, 기본 None=ALL).
        stage_specs: 사용자 지정 단계 스펙(설정 기능 §5-1a).
        rng: Stage A 후보 셔플 RNG. None이면 매 호출 새 시드(운영: 변주). 동일 시드 → 재현.
        lyric_scores: {song.idx: 가사 코사인 유사도}. None이면 Stage C를 건너뛴다(이 경우
            build_setlist()와 완전히 동일하게 동작 — 패스스루 테스트용).

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

    # ── Stage C: SELECT-CANDIDATES — 가사 코사인 유사도 상위 N으로 pool 축소(Stage A 직전) ──
    # DESIGN_v3.md §0: N = max(15, ceil(0.20 * |pool|)) — v1 arm2와 동일 공식(DESIGN.md §3).
    if lyric_scores is not None:
        n_candidates = max(15, math.ceil(0.20 * len(pool)))
        pool = sorted(pool, key=lambda s: -lyric_scores.get(s.idx, -1.0))[:n_candidates]

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

    # ── Stage B: SEQUENCE — 곡 경계 텐션 연속성 체인(이전 아웃트로 ↔ 다음 인트로) ──
    stages_out: list[Stage] = []
    picks: list[Pick] = []
    prev: Song | None = None
    position = 0
    prev_outro: float | None = None  # 직전 스테이지 마지막 곡의 아웃트로 텐션(경계 접합용)

    for stage_index, (target, members) in enumerate(zip(targets, stage_members)):
        stages_out.append(Stage(index=stage_index, energy_target=round(target, 4)))
        if not members:
            continue
        seq = _sequence_by_continuity(members, target, prev_outro, rng)
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
        prev_outro = seq[-1].outro_energy

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
