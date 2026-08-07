"""선곡 엔진 — `build_setlist()` 순수·결정적 함수 (진입점).

2단계 설계(R&D 보고서 document-archive 브랜치 archive/last-papers/research/2026-07-11-playlist-sequencing-strategy.md §2):
- **Stage A — SELECT**: 각 단계 강도(intensity) 목표에 부합하는 곡을 하드하게 선택(무드 누출 차단).
- **Stage B — SEQUENCE**: 이미 무드가 맞는 곡을 가중 특징공간에서 HAM-2로 정렬(전환 매끄러움).

두 목표를 서로 다른 단계에서 각각 보장하므로 충돌하지 않는다. LLM 출력(MoodParameters)만
입력받으며 외부 서비스에 의존하지 않는다. 시드 고정 시 동일 입력 → 동일 출력(결정적).
`Song.energy`는 강도(intensity, 0~1) — song_repo가 percentile+power-mean으로 산출.
"""

from __future__ import annotations

import random

from .energy import (
    continuous_slot_targets,
    distribute_counts,
    distribute_counts_by_weights,
    stage_energy_targets,
    total_song_count,
)
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

# 3.5단계(2026-08-04): stage_specs/stage_params의 신규 오디오 지표 6종(연구 채택,
# audio_feats_revised) — 지금까지 echo 전용이었으나, 이제 Stage A 소프트 매칭에도 반영한다.
# Song에 해당 컬럼이 없는(구 스냅샷·테스트 픽스처) 곡·요청은 값이 None이라 자동으로 무시된다
# (에너지 하드 필터·밝기 소프트 정렬은 그대로 유지 — 이 지표들은 그 다음 3순위 타이브레이커).
_NEW_STAGE_PARAM_FIELDS = (
    "valence", "lufs_integrated", "lra",
    "danceability_norm", "instr_stem_ratio", "speech_median",
)

# 2단계 엔진 파라미터(R&D §4.2 권장 기본값). 파일럿 후 실사용 피드백으로 튜닝.
_TOL = 0.08              # Stage A 강도 허용창(목표에서 이 이내만 후보)
# 완충 노드(4-5단계 사이, hotfix/boundary-tension 논의): 허용창 밖으로 폴백된 픽 중에서도
# 이탈이 이 이상이면 억지로 채우지 않고 슬롯을 건너뛴다(자동 축소) — 밴드 필터 등으로 풀이
# 좁을 때 "조용 요청인데 안 조용한 곡"이 섞이는 걸 막는다. 이 값 이하는 채우되 degraded로 표시.
_HARD_TOL = 2 * _TOL
_BRIGHTNESS_BUCKET = 0.25  # Stage A 밝기 근접 버킷 폭(같은 버킷 내에선 rng 변주)
# Stage B 시퀀싱: 경계갭 + 하모닉 + 강도순서이탈을 다목적 비용으로 최소화. (검증 하네스로 튜닝 — R&D §8.)
_RANDOM_SLACK = 0.05     # 최소 비용 대비 이 범위 내 후보는 랜덤(곡 선택 변주는 Stage A가 담당)
_HARMONIC_PENALTY = 0.15  # 비하모닉 전환 비용(경계갭과 동일 단위; 경계 최소화와 하모닉 균형점)
# feature/energy-stream: Stage A가 슬롯별로 부드럽게 매칭해둔 곡을, Stage B가 경계텐션만
# 보고 순서를 재배치하면서 강도 흐름이 다시 계단(더 나쁘면 요철)처럼 튀는 문제를 막기 위한
# 가중치 — 후보의 energy가 이 슬롯의 목표(continuous_slot_targets)에서 멀수록 비용 가산.
_ENERGY_ORDER_WEIGHT = 1.5


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
    slot_targets: list[float] | None = None,
) -> list[Song]:
    """곡 경계 텐션 연속성 기반 방향성 그리디 체인(사용자 §종합, 2026-07-11).

    이전 곡 **아웃트로 텐션 ↔ 다음 곡 인트로 텐션**의 차이를 최소화하도록 이어붙인다. 곡 *내부*
    텐션 변동은 정상으로 보고 무시하며, 오직 곡 *경계*의 급차이만 줄인다.

    - seed: 이전 스테이지 아웃트로가 있으면 그와 인트로가 가장 가까운 곡(경계 접합), 없으면(첫
      스테이지) 단계 강도 목표 근접 곡.
    - 이후: 직전 곡 아웃트로와 인트로 차가 최소인 후보(±`_CONT_WINDOW`) 중, 하모닉 호환을
      소프트 우선하고 그 안에서 랜덤 선택(사용자 '랜덤 셀렉트' + 다양성).

    `slot_targets`(feature/energy-stream, 이 스테이지분 `continuous_slot_targets` 구간)를 주면,
    Stage A가 슬롯별로 매칭해둔 강도 순서를 Stage B가 텐션 이음새만 보고 뒤섞지 않도록 각
    위치의 비용에 "이 슬롯 목표에서 얼마나 먼가"도 반영한다. 없으면(레거시 호출) 기존과 동일.
    """
    if prev_outro is None:
        # 오프너(전체 첫 곡): 강도 부합 후보 중 **인트로 텐션이 가장 높은** 곡으로 시드한다
        # (에너지 있는 시작 — 파티/운동 요청의 조용한 인트로 오프너 문제 해소, R&D §8-3).
        by_fit = sorted(members, key=lambda s: (abs(s.energy - target), s.idx))
        fit_window = [s for s in by_fit if abs(s.energy - target) <= _TOL] or by_fit[:5]
        seed = max(fit_window, key=lambda s: (s.intro_energy, -s.idx))
    else:
        # 스테이지 경계 접합: 이전 스테이지 아웃트로와 인트로가 가깝고, 이 스테이지 첫
        # 슬롯의 목표 강도에도 가까운 곡(둘 다 반영, 순수 텐션 하나만으로 강도 순서가
        # 깨지지 않게).
        seed_target = slot_targets[0] if slot_targets else target
        seed = min(
            members,
            key=lambda s: (
                abs(prev_outro - s.intro_energy) + _ENERGY_ORDER_WEIGHT * abs(s.energy - seed_target),
                s.idx,
            ),
        )
    seq = [seed]
    rem = [s for s in members if s.idx != seed.idx]
    while rem:
        current = seq[-1]
        position = len(seq)  # 다음에 채울 슬롯 인덱스
        slot_target = (
            slot_targets[position] if slot_targets and position < len(slot_targets) else target
        )

        def cost(candidate: Song, cur: Song = current, st: float = slot_target) -> float:
            gap = abs(cur.outro_energy - candidate.intro_energy)
            penalty = 0.0 if is_compatible(cur.camelot, candidate.camelot) else _HARMONIC_PENALTY
            order_penalty = _ENERGY_ORDER_WEIGHT * abs(candidate.energy - st)
            return gap + penalty + order_penalty

        rem.sort(key=lambda c: (cost(c), c.idx))
        best = cost(rem[0])
        window = [c for c in rem if cost(c) <= best + _RANDOM_SLACK]
        pick = rng.choice(window)
        seq.append(pick)
        rem.remove(pick)

    if slot_targets:
        # feature/energy-stream: 탐욕 체인은 뒤로 갈수록 남은 후보가 줄어(마지막 슬롯은 종종
        # 선택지가 1개뿐) 강제로 나쁜 배치가 남는다 — 2-opt로 국소 개선한다.
        seq = _local_refine_order(seq, slot_targets)
    return seq


_MAX_LOCAL_REFINE_SIZE = 40  # 이보다 큰 스테이지는 O(n^3) 스왑 탐색을 건너뛴다(그리디 결과 유지)


def _stage_sequence_cost(seq: list[Song], slot_targets: list[float]) -> float:
    """스테이지 내 시퀀스 하나의 총비용(경계갭+하모닉+슬롯목표 이탈 합)."""
    cost = 0.0
    for i in range(len(seq) - 1):
        cur, nxt = seq[i], seq[i + 1]
        cost += abs(cur.outro_energy - nxt.intro_energy)
        if not is_compatible(cur.camelot, nxt.camelot):
            cost += _HARMONIC_PENALTY
    for i, s in enumerate(seq):
        if i < len(slot_targets):
            cost += _ENERGY_ORDER_WEIGHT * abs(s.energy - slot_targets[i])
    return cost


def _local_refine_order(seq: list[Song], slot_targets: list[float], max_passes: int = 3) -> list[Song]:
    """2-opt 스왑으로 탐욕 체인 결과를 국소 개선(feature/energy-stream).

    탐욕 알고리즘은 뒤쪽 슬롯일수록 후보가 고갈돼(마지막 슬롯은 종종 후보 1개뿐) 강도
    순서에서 크게 벗어난 곡이 강제로 남을 수 있다 — 총비용이 줄어드는 두 위치 교환을
    개선이 없을 때까지(또는 `max_passes`까지) 반복 적용해 보정한다. 큰 스테이지
    (`_MAX_LOCAL_REFINE_SIZE` 초과)는 O(n^3) 탐색 비용을 피해 건너뛴다.
    """
    n = len(seq)
    if n < 3 or n > _MAX_LOCAL_REFINE_SIZE:
        return seq
    best = list(seq)
    best_cost = _stage_sequence_cost(best, slot_targets)
    for _ in range(max_passes):
        improved = False
        for i in range(n):
            for j in range(i + 1, n):
                candidate = list(best)
                candidate[i], candidate[j] = candidate[j], candidate[i]
                c = _stage_sequence_cost(candidate, slot_targets)
                if c < best_cost - 1e-9:
                    best, best_cost = candidate, c
                    improved = True
        if not improved:
            break
    return best


def _make_reason(
    energy_target: float,
    picked: Song,
    picked_brightness: float,
    brightness_target: float,
    prev: Song | None,
    harmonic: str,
    stage_index: int,
    degraded: bool = False,
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
    if degraded:
        text += " (후보 풀 부족으로 목표 강도에서 다소 벗어난 곡)"
    return PickReason(
        stage_energy_target=round(energy_target, 4),
        matched_energy=round(picked.energy, 4),
        harmonic=harmonic,
        prev_camelot=(prev.camelot if prev is not None else None),
        brightness_fit=brightness_fit,
        text=text,
        degraded=degraded,
    )


def _resolve_stage_target_params(
    stage_index: int,
    stage_specs: list[StageSpec] | None,
    params: MoodParameters,
) -> dict[str, float | str | None]:
    """스테이지 하나의 신규 지표 6종 + 가사 감상(impression) 목표값을 결정한다(스펙 우선,
    그다음 LLM stage_params).

    Stage A(선곡)·Stage 리포트(echo) 양쪽에서 동일한 우선순위 규칙을 쓰기 위해 분리(이전엔
    build_setlist 안의 클로저 `_field()`가 리포트 용도로만 있었다 — 이제 선곡에도 같은 값을
    써야 하므로 루프 시작 전에 한 번만 계산해 재사용한다).

    `impression`도 6개 수치와 동일한 우선순위(스펙 우선 → LLM stage_params 폴백)를 따른다 —
    커스텀 모드 사용자가 직접 입력한 텍스트가 있으면 그걸 쓰고, 없으면 AI 모드 해석 결과를 쓴다.
    `_stage_param_distance`는 `_NEW_STAGE_PARAM_FIELDS`(수치 6종)만 순회하므로 이 키가 섞여
    있어도 안전하게 무시된다.
    """
    spec = stage_specs[stage_index] if stage_specs else None
    llm_stage = (
        params.stage_params[stage_index]
        if params.stage_params and stage_index < len(params.stage_params)
        else None
    )
    resolved: dict[str, float | str | None] = {}
    for field in _NEW_STAGE_PARAM_FIELDS:
        value = getattr(spec, field) if spec is not None else None
        if value is None and llm_stage is not None:
            value = llm_stage.get(field)
        resolved[field] = value
    spec_impression = getattr(spec, "impression", None) if spec is not None else None
    resolved["impression"] = spec_impression or (
        llm_stage.get("impression") if llm_stage is not None else None
    )
    return resolved


def resolve_stage_impression_text(
    stage_index: int,
    stage_specs: list[StageSpec] | None,
    params: MoodParameters,
) -> str | None:
    """스테이지 하나의 가사 감상 텍스트를 우선순위 규칙대로 해석한다(공개 API).

    라우트가 `build_setlist()` 호출 전에 이 텍스트를 임베딩 어댑터로 벡터화해 넘겨야 하므로
    (도메인은 임베딩 모델을 모름), `_resolve_stage_target_params`와 동일한 규칙을 노출하는
    얇은 래퍼 — 로직 중복 없이 라우트가 재사용한다.
    """
    return _resolve_stage_target_params(stage_index, stage_specs, params)["impression"]


def _stage_param_distance(song: Song, target: dict[str, float | None]) -> float:
    """곡의 신규 지표 6종과 목표값의 평균 절대거리(사용 가능한 필드만, 없으면 0=중립)."""
    diffs = []
    for field in _NEW_STAGE_PARAM_FIELDS:
        t = target.get(field)
        v = getattr(song, field)
        if t is None or v is None:
            continue
        diffs.append(abs(v - t))
    return sum(diffs) / len(diffs) if diffs else 0.0


def _lyric_similarity(song: Song, target_vec: list[float] | None) -> float:
    """곡의 가사 감상 임베딩과 스테이지 목표 임베딩의 코사인 유사도(프로토타입, 4순위 타이브레이크).

    둘 다 사전 L2-정규화되어 있다고 가정(어댑터·오프라인 스크립트가 보장) — 그러면 코사인
    유사도는 단순 내적과 같다. `song.lyric_vec`나 `target_vec` 중 하나라도 없으면(가사
    매칭 데이터 없는 곡, LLM이 impression을 못 채운 경우) `0.0`(중립) — 기존 3개 우선순위
    (energy 하드필터·밝기·6개 수치 지표)만으로 동작하던 기존 흐름을 그대로 보존한다.
    """
    if song.lyric_vec is None or target_vec is None:
        return 0.0
    return sum(a * b for a, b in zip(song.lyric_vec, target_vec))


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
        # 비단조 아크(LLM 산출): 단계별 에너지 배열을 그대로 목표로.
        targets = [_clamp(e, 0.0, 1.0) for e in params.stage_energies]
        n = len(targets)
        total = min(total_song_count(target_seconds, avg_song_seconds, n), pool_size)
        # 3.5단계: 단계별 길이(분) 의도가 있으면 곡 수를 그 비율로 배분("마지막 5분은
        # 릴랙스" 같은 요청이 균등분배로 뭉개지지 않도록). 길이가 안 맞으면(모델이 배열
        # 길이를 못 맞춤) 신뢰하지 않고 기존 균등분배로 폴백.
        if params.stage_minutes and len(params.stage_minutes) == n:
            return targets, distribute_counts_by_weights(total, params.stage_minutes)
        return targets, distribute_counts(total, n)
    targets = stage_energy_targets(params.start_energy, params.end_energy, params.stage_count)
    total = min(total_song_count(target_seconds, avg_song_seconds, params.stage_count), pool_size)
    if params.stage_minutes and len(params.stage_minutes) == params.stage_count:
        counts = distribute_counts_by_weights(total, params.stage_minutes)
    else:
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
    stage_impression_vectors: list[list[float] | None] | None = None,
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
        stage_impression_vectors: 스테이지별 가사 감상 목표 임베딩(프로토타입). 라우트가
            `MoodParameters.stage_params[i]["impression"]`을 임베딩 어댑터로 미리 벡터화해
            넘긴다(도메인은 임베딩 모델을 직접 호출하지 않음 — 클린 아키텍처 불변식). 길이는
            stage_count와 같아야 하며, 인덱스가 벗어나거나 항목이 None이면 그 스테이지는
            가사 유사도 타이브레이크 없이(중립) 기존 동작 그대로.

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
    # 3.5단계: 스테이지별 신규 지표 6종 목표값을 미리 한 번 계산(Stage A 매칭 + Stage 리포트
    # 양쪽에서 재사용 — 우선순위 규칙 이원화 방지).
    stage_target_params = [
        _resolve_stage_target_params(i, stage_specs, params) for i in range(len(targets))
    ]

    # ── Stage A: SELECT — 곡 하나하나를 스테이지 경계에서 부드럽게 흐르는 목표에 매칭 ──
    # feature/energy-stream: 스테이지 전체에 flat 목표 하나만 쓰던 기존 방식 대신, 곡
    # 슬롯마다 continuous_slot_targets()로 보간한 목표값을 쓴다 — 그래프가 스테이지 중앙을
    # 스플라인으로 잇는 시각(부드러운 곡선)과 실제 곡 강도 전환을 일치시킨다. 보고용
    # Stage.energy_target은 원래 flat targets 그대로(그래프 호환 유지, 아래서 별도 사용).
    slot_targets = continuous_slot_targets(targets, counts)
    remaining = {s.idx: s for s in pool}
    stage_members: list[list[Song]] = []
    degraded_idx: set[int] = set()  # 허용창 밖이지만 채택된 픽(완충 노드가 표시만 하는 케이스)
    slot = 0
    for stage_index, count in enumerate(counts):
        chosen: list[Song] = []
        target_params = stage_target_params[stage_index]
        stage_target_vec = (
            stage_impression_vectors[stage_index]
            if stage_impression_vectors and stage_index < len(stage_impression_vectors)
            else None
        )
        for _ in range(count):
            if not remaining:
                break
            slot_target = slot_targets[slot]
            slot += 1
            cand = sorted(remaining.values(), key=lambda s: (abs(s.energy - slot_target), s.idx))
            window = [s for s in cand if abs(s.energy - slot_target) <= _TOL]
            if window:
                # 허용창 내 곡은 모두 무드 부합 → rng 셔플로 변주 후 밝기 버킷 근접 우선(재현적),
                # 그다음 신규 지표 6종(valence 등) 거리로 타이브레이크(3.5단계 — 지표 없는
                # 곡/요청이면 거리 0이라 이 tiebreak는 자동으로 무력화되고 기존 동작 그대로),
                # 마지막으로 가사 감상 임베딩 유사도(프로토타입, 4순위 — 벡터 없으면 0.0 중립).
                rng.shuffle(window)
                window.sort(key=lambda s: (
                    round(abs(brightness[s.idx] - params.brightness) / _BRIGHTNESS_BUCKET),
                    round(_stage_param_distance(s, target_params), 4),
                    -_lyric_similarity(s, stage_target_vec),
                ))
                pick = window[0]
            else:
                # 완충 노드: 허용창 밖 최근접 후보. 이탈이 _HARD_TOL을 넘으면 억지로 채우지
                # 않고 이 슬롯을 건너뛴다 — 목표 곡 수가 풀 크기에 맞게 자동으로 줄어든다
                # (좁은 밴드 필터 등으로 "조용 요청인데 시끄러운 곡 섞임" 방지).
                closest = cand[0]
                if abs(closest.energy - slot_target) > _HARD_TOL:
                    continue
                pick = closest
                degraded_idx.add(pick.idx)
            del remaining[pick.idx]
            chosen.append(pick)
        stage_members.append(chosen)

    # ── Stage B: SEQUENCE — 곡 경계 텐션 연속성 체인(이전 아웃트로 ↔ 다음 인트로) ──
    stages_out: list[Stage] = []
    picks: list[Pick] = []
    prev: Song | None = None
    position = 0
    prev_outro: float | None = None  # 직전 스테이지 마지막 곡의 아웃트로 텐션(경계 접합용)
    slot_cursor = 0  # slot_targets에서 이 스테이지가 차지하는 구간 추적(Stage A와 동일 순서)

    for stage_index, (target, members) in enumerate(zip(targets, stage_members)):
        # stage_specs(사용자 지정, 커스텀 모드 등)가 최우선, 없으면 LLM stage_params 폴백 —
        # Stage A에서 이미 쓴 것과 동일한 stage_target_params[stage_index]를 그대로 echo.
        target_params = stage_target_params[stage_index]
        stages_out.append(Stage(
            index=stage_index,
            energy_target=round(target, 4),
            valence=target_params["valence"],
            lufs_integrated=target_params["lufs_integrated"],
            lra=target_params["lra"],
            danceability_norm=target_params["danceability_norm"],
            instr_stem_ratio=target_params["instr_stem_ratio"],
            speech_median=target_params["speech_median"],
            impression=target_params["impression"],
        ))
        if not members:
            continue
        stage_slot_targets = slot_targets[slot_cursor : slot_cursor + len(members)]
        slot_cursor += len(members)
        seq = _sequence_by_continuity(members, target, prev_outro, rng, slot_targets=stage_slot_targets)
        for s in seq:
            harmonic = harmonic_label(None if prev is None else prev.camelot, s.camelot)
            reason = _make_reason(
                target, s, brightness[s.idx], params.brightness, prev, harmonic, stage_index,
                degraded=s.idx in degraded_idx,
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
