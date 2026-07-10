"""선곡 엔진 테스트 (도메인 순수 — 결정적성·중복 방지·하모닉 우선·필터)."""

import random
from collections import Counter

import pytest

from app.domain.models import MoodParameters, NoSetlistError, Song, StageSpec
from app.domain.selection import build_setlist


def _songs() -> list[Song]:
    # (idx, band, camelot, energy, mode_score, shape, eligible)
    rows = [
        (0, "a", "8A", 0.10, -1.0, "acoustic", True),
        (1, "a", "8B", 0.20, -0.5, "neutral", True),
        (2, "a", "9A", 0.30, 0.0, "neutral", True),
        (3, "b", "9B", 0.40, 0.2, "bright", True),
        (4, "b", "7A", 0.50, 0.5, "bright", True),
        (5, "b", "7B", 0.55, 0.8, "shimmer", True),
        (6, "c", "10A", 0.60, 1.0, "shimmer", True),
        (7, "c", "10B", 0.70, 0.3, "neutral", True),
        (8, "c", "6A", 0.80, -0.2, "acoustic", True),
        (9, "a", "6B", 0.85, 0.1, "bright", True),
        (10, "b", "11A", 0.90, 0.6, "shimmer", True),
        (11, "c", "11B", 0.95, -0.8, "neutral", True),
        (12, "d", "3B", 0.45, 0.0, "neutral", False),  # 후보 제외 대상
    ]
    return [
        Song(idx=i, band=b, song=f"song{i}", video_id=f"vid{i:07d}0", camelot=c,
             energy=e, mode_score=m, shape=sh, eligible_band=el)
        for (i, b, c, e, m, sh, el) in rows
    ]


def _params(stage_count=3, start=0.2, end=0.9) -> MoodParameters:
    return MoodParameters(
        brightness=0.5, start_energy=start, end_energy=end,
        stage_count=stage_count, target_minutes=None, interpretation_summary="test",
    )


def test_seeded_reproducible():
    # 동일 시드 → 동일 출력(확률적이지만 재현 가능).
    songs, params = _songs(), _params()
    a = build_setlist(songs, params, target_seconds=6 * 213, rng=random.Random(42))
    b = build_setlist(songs, params, target_seconds=6 * 213, rng=random.Random(42))
    assert [p.idx for p in a.picks] == [p.idx for p in b.picks]


def test_different_seeds_can_differ():
    songs, params = _songs(), _params()
    orders = {
        tuple(p.idx for p in build_setlist(songs, params, target_seconds=8 * 213, rng=random.Random(s)).picks)
        for s in range(12)
    }
    assert len(orders) > 1  # 시드가 다르면 결과가 갈릴 수 있음(다양성)


def test_probabilistic_target_shapes_energy():
    # 낮은 에너지 목표는 더 낮은 에너지 곡을, 높은 목표는 더 높은 에너지 곡을 선호해야 한다.
    songs, params = _songs(), _params()
    by_idx = {s.idx: s for s in songs}

    def avg_energy_for(target: float) -> float:
        picks: Counter[int] = Counter()
        for seed in range(150):
            specs = [StageSpec(energy_target=target, song_count=1)]
            sl = build_setlist(songs, params, target_seconds=999, stage_specs=specs, rng=random.Random(seed))
            picks[sl.picks[0].idx] += 1
        return sum(by_idx[i].energy * c for i, c in picks.items()) / sum(picks.values())

    assert avg_energy_for(0.1) < avg_energy_for(0.9)


def test_max_probability_capped():
    # 한 곡이 압도적으로 부합해도 단독 선택 확률이 상한(0.30) 근처로 제한되어야 한다.
    songs = [
        Song(0, "a", "perfect", "vid0000000", "8A", 0.50, 0.0, "neutral", eligible_band=True),
        Song(1, "b", "x1", "vid0000001", "3A", 0.05, -1.0, "acoustic", eligible_band=True),
        Song(2, "c", "x2", "vid0000002", "6B", 0.95, 1.0, "bright", eligible_band=True),
        Song(3, "d", "x3", "vid0000003", "1A", 0.03, -0.9, "acoustic", eligible_band=True),
        Song(4, "e", "x4", "vid0000004", "11B", 0.98, 0.9, "bright", eligible_band=True),
    ]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5,
        stage_count=1, target_minutes=None, interpretation_summary="",
    )
    first: Counter[int] = Counter()
    trials = 400
    for seed in range(trials):
        specs = [StageSpec(energy_target=0.5, song_count=1)]
        sl = build_setlist(songs, params, target_seconds=999, stage_specs=specs, rng=random.Random(seed))
        first[sl.picks[0].idx] += 1
    # 완벽 부합 곡(idx 0)이라도 상한(0.30) 덕에 절반을 넘지 못한다.
    assert first[0] / trials <= 0.42


def test_no_duplicate_songs():
    setlist = build_setlist(_songs(), _params(), target_seconds=8 * 213)
    idxs = [p.idx for p in setlist.picks]
    assert len(idxs) == len(set(idxs))


def test_ineligible_band_excluded():
    setlist = build_setlist(_songs(), _params(), target_seconds=12 * 213)
    assert all(p.idx != 12 for p in setlist.picks)  # idx 12 = eligible_band False


def test_first_pick_is_seed():
    setlist = build_setlist(_songs(), _params(), target_seconds=6 * 213)
    assert setlist.picks[0].reason.harmonic == "seed"
    assert setlist.picks[0].reason.prev_camelot is None


def test_stages_energy_targets_ascending():
    setlist = build_setlist(_songs(), _params(start=0.2, end=0.9), target_seconds=6 * 213)
    targets = [s.energy_target for s in setlist.stages]
    assert targets == sorted(targets)
    assert len(setlist.stages) == 3


def test_band_filter_restricts_pool():
    setlist = build_setlist(_songs(), _params(), target_seconds=3 * 213, band_filter={"a"})
    assert {p.band for p in setlist.picks} == {"a"}


def test_harmonic_preference_prefers_adjacency():
    # 하모닉은 하드 필터가 아니라 가중치(×4). 전환의 상당수가 same/adjacent 여야 한다.
    setlist = build_setlist(_songs(), _params(), target_seconds=6 * 213, rng=random.Random(0))
    transitions = [p.reason.harmonic for p in setlist.picks[1:]]
    harmonic_ok = sum(1 for h in transitions if h in ("same", "adjacent"))
    assert harmonic_ok >= len(transitions) // 3


def test_estimated_total_seconds_uses_avg():
    setlist = build_setlist(_songs(), _params(), target_seconds=6 * 213, avg_song_seconds=200)
    assert setlist.estimated_total_seconds == len(setlist.picks) * 200


def test_empty_pool_raises_no_setlist():
    with pytest.raises(NoSetlistError):
        build_setlist([], _params(), target_seconds=6 * 213)


def test_all_ineligible_raises_no_setlist():
    songs = [Song(0, "a", "song", "vid0000000", "8A", 0.5, 0.0, "neutral", eligible_band=False)]
    with pytest.raises(NoSetlistError):
        build_setlist(songs, _params(), target_seconds=6 * 213)


def test_stage_specs_override_energy_and_counts():
    # 사용자 지정 단계: 에너지·곡 수를 그대로 강제(설정 §5-1a).
    specs = [StageSpec(energy_target=0.1, song_count=2), StageSpec(energy_target=0.9, song_count=3)]
    setlist = build_setlist(_songs(), _params(), target_seconds=999, stage_specs=specs)
    assert [s.energy_target for s in setlist.stages] == [0.1, 0.9]
    assert len(setlist.picks) == 5
    assert sum(1 for p in setlist.picks if p.stage_index == 0) == 2
    assert sum(1 for p in setlist.picks if p.stage_index == 1) == 3


def test_stage_specs_energy_clamped():
    specs = [StageSpec(energy_target=5.0, song_count=1), StageSpec(energy_target=-3.0, song_count=1)]
    setlist = build_setlist(_songs(), _params(), target_seconds=999, stage_specs=specs)
    assert [s.energy_target for s in setlist.stages] == [1.0, 0.0]
