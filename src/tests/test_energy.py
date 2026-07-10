"""에너지 목표·곡 수 산정 테스트 (도메인 순수)."""

import pytest

from app.domain.energy import distribute_counts, stage_energy_targets, total_song_count


def test_targets_linear_interpolation():
    targets = stage_energy_targets(0.3, 0.9, 3)
    assert targets == pytest.approx([0.3, 0.6, 0.9])


def test_single_stage_returns_start():
    assert stage_energy_targets(0.5, 0.9, 1) == [0.5]


def test_flat_arc_when_start_equals_end():
    assert stage_energy_targets(0.4, 0.4, 4) == pytest.approx([0.4, 0.4, 0.4, 0.4])


def test_descending_arc():
    targets = stage_energy_targets(0.8, 0.2, 3)
    assert targets == pytest.approx([0.8, 0.5, 0.2])


def test_total_song_count_60min():
    # 3600s / 213s ≈ 17곡
    assert total_song_count(3600, 213, 3) == 17


def test_total_song_count_min_stage_floor():
    # 아주 짧은 목표라도 단계당 최소 1곡(= stage_count) 보장
    assert total_song_count(60, 213, 3) == 3


def test_distribute_even_with_remainder():
    counts = distribute_counts(17, 3)
    assert counts == [6, 6, 5]
    assert sum(counts) == 17


def test_distribute_min_one_per_stage():
    counts = distribute_counts(3, 3)
    assert counts == [1, 1, 1]
