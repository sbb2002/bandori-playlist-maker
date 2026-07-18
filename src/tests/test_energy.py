"""에너지 목표·곡 수 산정 테스트 (도메인 순수)."""

import pytest

from app.domain.energy import (
    continuous_slot_targets,
    distribute_counts,
    stage_energy_targets,
    total_song_count,
)


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


# ── continuous_slot_targets (feature/energy-stream §b) ────────────────────────
# 그래프가 스테이지 중앙을 스플라인으로 잇는 시각과 실제 선곡 기준값을 맞추기 위한 보간.

def test_continuous_slot_targets_single_stage_is_flat():
    assert continuous_slot_targets([0.5], [4]) == [0.5, 0.5, 0.5, 0.5]


def test_continuous_slot_targets_empty_when_no_songs():
    assert continuous_slot_targets([0.2, 0.5], [0, 0]) == []


def test_continuous_slot_targets_smooth_across_boundary():
    # 3스테이지(0.2/0.5/0.8) × 4곡 = 12슬롯. 스테이지 중앙(1.5, 5.5, 9.5)에서 정확히 flat
    # 값과 만나고, 경계에 가까운 슬롯일수록 이웃 스테이지 쪽으로 값이 기운다(계단식이 아님).
    slots = continuous_slot_targets([0.2, 0.5, 0.8], [4, 4, 4])
    assert len(slots) == 12
    assert slots[0] == pytest.approx(0.2)  # 첫 곡: 첫 스테이지 값에서 시작
    assert slots[11] == pytest.approx(0.8)  # 마지막 곡: 마지막 스테이지 값으로 종료
    # 스테이지0(0~3)의 마지막 곡은 flat 0.2보다 이미 스테이지1 쪽으로 올라가 있어야 한다.
    assert 0.2 < slots[3] < 0.5
    # 스테이지1(4~7)의 첫 곡은 flat 0.5보다 낮게(스테이지0 여운) 시작해야 한다.
    assert 0.2 < slots[4] < 0.5
    # 슬롯 전체가 계단 없이 단조증가(경계에서 뚝 끊기지 않음의 직접적 증거).
    assert all(b >= a for a, b in zip(slots, slots[1:]))


def test_continuous_slot_targets_hits_stage_value_at_center_index():
    # counts가 홀수면 스테이지 중앙이 정수 인덱스와 정확히 겹쳐 flat 값과 100% 일치해야 한다.
    slots = continuous_slot_targets([0.2, 0.5, 0.8], [3, 3, 3])
    assert slots[1] == pytest.approx(0.2)  # 스테이지0 중앙 = 인덱스 1
    assert slots[4] == pytest.approx(0.5)  # 스테이지1 중앙 = 인덱스 4
    assert slots[7] == pytest.approx(0.8)  # 스테이지2 중앙 = 인덱스 7
