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


def continuous_slot_targets(targets: list[float], counts: list[int]) -> list[float]:
    """스테이지별 flat 목표(targets)를 곡 하나하나 단위로 부드럽게 보간한다(feature/energy-stream).

    프론트 에너지 그래프(app.js renderStageGraph)는 각 스테이지 값을 그 스테이지의 시간
    중앙점에 찍고 스플라인으로 잇는다 — 그런데 기존 선곡 로직은 스테이지 전체에 flat한
    목표 하나만 써서, 그래프는 부드러운데 실제 곡 강도 전환은 스테이지 경계에서 계단식으로
    뚝 끊겼다. 이 함수는 그 간극을 메운다: 스테이지 중앙(곡 인덱스 기준)을 앵커로 두고
    조각별 선형보간한 값을 곡 '슬롯'마다 산출해, 경계 근처 곡들이 이웃 스테이지 쪽으로
    서서히 흘러가게 한다.

    `Stage.energy_target`(API 응답 보고값, 그래프가 그대로 쓰는 값)은 이 함수와 무관하게
    원래 flat `targets` 그대로 유지된다 — 이건 오직 Stage A 곡 매칭 기준값에만 쓰인다.
    """
    n = len(targets)
    total = sum(counts)
    if total <= 0:
        return []
    if n == 1:
        return [targets[0]] * total

    cum = [0]
    for c in counts:
        cum.append(cum[-1] + c)
    # 스테이지 중앙 = 그 스테이지에 속한 곡 인덱스 구간의 중앙(0-indexed). 곡이 0개인
    # 스테이지(작은 pool 등 예외 상황)는 그 시점의 누적 경계를 대신 앵커로 쓴다.
    centers = [
        (cum[i] + cum[i + 1] - 1) / 2 if counts[i] > 0 else float(cum[i])
        for i in range(n)
    ]

    anchors_x = [0.0] + centers + [float(total - 1)]
    anchors_y = [targets[0]] + list(targets) + [targets[-1]]
    # 곡이 0개인 스테이지가 연속되면 앵커가 역행할 수 있어 방어적으로 단조증가를 강제한다.
    for i in range(1, len(anchors_x)):
        if anchors_x[i] < anchors_x[i - 1]:
            anchors_x[i] = anchors_x[i - 1]

    return [_piecewise_linear(float(k), anchors_x, anchors_y) for k in range(total)]


def _piecewise_linear(x: float, xs: list[float], ys: list[float]) -> float:
    """앵커 점(xs, ys) 사이를 조각별 선형보간(구간 밖은 양 끝값으로 클램프)."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i + 1]:
            span = xs[i + 1] - xs[i]
            if span <= 0:
                return ys[i]
            t = (x - xs[i]) / span
            return ys[i] + (ys[i + 1] - ys[i]) * t
    return ys[-1]
