"""단계별 에너지 목표 산출 + 곡 수 산정 (순수 함수).

architecture.md §③ 스키마2 알고리즘 3·4에 해당.
"""

from __future__ import annotations


def stage_energy_targets(start_energy: float, end_energy: float, stage_count: int) -> list[float]:
    """N단계 각각의 에너지 목표를 선형 보간으로 산출한다.

    target[i] = start + (end - start) * i / (N - 1)

    N=1이면 [start] 단일 값. start==end면 전 단계 동일(플랫) 아크.
    """
    if stage_count <= 0:
        raise ValueError(f"stage_count must be >= 1, got {stage_count}")
    if stage_count == 1:
        return [start_energy]
    span = end_energy - start_energy
    return [start_energy + span * i / (stage_count - 1) for i in range(stage_count)]


def total_song_count(target_seconds: int, avg_song_seconds: int, stage_count: int) -> int:
    """목표 재생시간에 맞는 총 곡 수. 단계당 최소 1곡을 보장한다."""
    if avg_song_seconds <= 0:
        raise ValueError(f"avg_song_seconds must be > 0, got {avg_song_seconds}")
    n = round(target_seconds / avg_song_seconds)
    return max(n, stage_count, 1)


def distribute_counts(total: int, stage_count: int) -> list[int]:
    """총 곡 수를 N단계에 최대한 균등 분배(나머지는 앞 단계부터)한다.

    `total >= stage_count`일 때 각 단계 곡 수 >= 1이 보장된다.
    """
    if stage_count <= 0:
        raise ValueError(f"stage_count must be >= 1, got {stage_count}")
    base = total // stage_count
    remainder = total % stage_count
    return [base + (1 if i < remainder else 0) for i in range(stage_count)]
