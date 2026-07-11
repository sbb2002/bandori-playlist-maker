"""선곡 엔진 테스트 (2단계 SELECT→SEQUENCE, 도메인 순수 — 네트워크·LLM 없음)."""

import random

import pytest

from app.domain.models import MoodParameters, NoSetlistError, Song, StageSpec
from app.domain.selection import build_setlist


def _songs() -> list[Song]:
    # (idx, band, camelot, intensity(=energy), mode_score, shape, eligible)
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


def _dense_pool(n: int = 30, intensity: float = 0.2) -> list[Song]:
    """모두 동일 강도(허용창 내)·다양한 밝기/조성의 곡 — 변주 검증용."""
    return [
        Song(idx=i, band=f"b{i % 4}", song=f"s{i}", video_id=f"vid{i:08d}", camelot=f"{(i % 12) + 1}{'A' if i % 2 else 'B'}",
             energy=intensity, mode_score=((i % 7) - 3) / 3.0, shape="neutral", eligible_band=True)
        for i in range(n)
    ]


def _params(stage_count=3, start=0.2, end=0.9) -> MoodParameters:
    return MoodParameters(
        brightness=0.3, start_energy=start, end_energy=end,
        stage_count=stage_count, target_minutes=None, interpretation_summary="test",
    )


def test_seeded_reproducible():
    songs, params = _songs(), _params()
    a = build_setlist(songs, params, target_seconds=6 * 213, rng=random.Random(42))
    b = build_setlist(songs, params, target_seconds=6 * 213, rng=random.Random(42))
    assert [p.idx for p in a.picks] == [p.idx for p in b.picks]


def test_variety_on_dense_pool():
    # 허용창이 충분히 크면(무드 부합 곡 다수) 시드마다 결과가 갈릴 수 있어야 한다(변주).
    pool = _dense_pool(30, intensity=0.2)
    params = MoodParameters(brightness=0.0, start_energy=0.2, end_energy=0.2,
                            stage_count=3, target_minutes=None, interpretation_summary="")
    orders = {
        tuple(p.idx for p in build_setlist(pool, params, target_seconds=6 * 213, rng=random.Random(s)).picks)
        for s in range(8)
    }
    assert len(orders) > 1


def test_no_duplicate_songs():
    setlist = build_setlist(_songs(), _params(), target_seconds=8 * 213, rng=random.Random(0))
    idxs = [p.idx for p in setlist.picks]
    assert len(idxs) == len(set(idxs))


def test_ineligible_band_excluded():
    setlist = build_setlist(_songs(), _params(), target_seconds=12 * 213, rng=random.Random(0))
    assert all(p.idx != 12 for p in setlist.picks)


def test_first_pick_is_seed():
    setlist = build_setlist(_songs(), _params(), target_seconds=6 * 213, rng=random.Random(0))
    assert setlist.picks[0].reason.harmonic == "seed"
    assert setlist.picks[0].reason.prev_camelot is None


def test_stages_ascending_and_grouped():
    setlist = build_setlist(_songs(), _params(start=0.2, end=0.9), target_seconds=6 * 213, rng=random.Random(0))
    targets = [s.energy_target for s in setlist.stages]
    assert targets == sorted(targets)
    stage_seq = [p.stage_index for p in setlist.picks]
    assert stage_seq == sorted(stage_seq)  # 단계별로 그룹핑되어 순서대로 방출


def test_band_filter_restricts_pool():
    setlist = build_setlist(_songs(), _params(), target_seconds=3 * 213, band_filter={"a"}, rng=random.Random(0))
    assert {p.band for p in setlist.picks} == {"a"}


def test_low_target_favors_low_intensity():
    songs = _songs()
    lo = build_setlist(songs, _params(start=0.15, end=0.15), target_seconds=3 * 213, rng=random.Random(1))
    hi = build_setlist(songs, _params(start=0.85, end=0.85), target_seconds=3 * 213, rng=random.Random(1))
    avg = lambda sl: sum(p.energy for p in sl.picks) / len(sl.picks)
    assert avg(lo) < avg(hi)


def test_stage_specs_override_energy_and_counts():
    specs = [StageSpec(energy_target=0.1, song_count=2), StageSpec(energy_target=0.9, song_count=3)]
    setlist = build_setlist(_songs(), _params(), target_seconds=999, stage_specs=specs, rng=random.Random(0))
    assert [s.energy_target for s in setlist.stages] == [0.1, 0.9]
    assert len(setlist.picks) == 5
    assert sum(1 for p in setlist.picks if p.stage_index == 0) == 2
    assert sum(1 for p in setlist.picks if p.stage_index == 1) == 3


def test_stage_energies_produce_nonmonotonic_arc():
    # 비단조 아크(유산소류): stage_energies가 선형 아크를 덮어써 단계 목표가 오르내린다.
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=3,
        target_minutes=None, interpretation_summary="", stage_energies=[0.2, 0.9, 0.3],
    )
    setlist = build_setlist(_songs(), params, target_seconds=9 * 213, rng=random.Random(0))
    assert [s.energy_target for s in setlist.stages] == [0.2, 0.9, 0.3]


def test_stage_specs_energy_clamped():
    specs = [StageSpec(energy_target=5.0, song_count=1), StageSpec(energy_target=-3.0, song_count=1)]
    setlist = build_setlist(_songs(), _params(), target_seconds=999, stage_specs=specs, rng=random.Random(0))
    assert [s.energy_target for s in setlist.stages] == [1.0, 0.0]


def test_estimated_total_seconds_uses_avg():
    setlist = build_setlist(_songs(), _params(), target_seconds=6 * 213, avg_song_seconds=200, rng=random.Random(0))
    assert setlist.estimated_total_seconds == len(setlist.picks) * 200


def test_empty_pool_raises_no_setlist():
    with pytest.raises(NoSetlistError):
        build_setlist([], _params(), target_seconds=6 * 213)


def test_all_ineligible_raises_no_setlist():
    songs = [Song(0, "a", "song", "vid0000000", "8A", 0.5, 0.0, "neutral", eligible_band=False)]
    with pytest.raises(NoSetlistError):
        build_setlist(songs, _params(), target_seconds=6 * 213)
