"""선곡 엔진 테스트 (2단계 SELECT→SEQUENCE, 도메인 순수 — 네트워크·LLM 없음)."""

import random

import pytest

from app.domain.models import MoodParameters, NoSetlistError, Song, StageSpec
from app.domain.selection import _local_refine_order, _stage_sequence_cost, build_setlist, resolve_stage_band


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


def _fine_grained_pool(n: int = 50) -> list[Song]:
    """0.00~0.98 사이 촘촘한 강도 값의 곡 풀(경계 보간 검증용, feature/energy-stream §b)."""
    return [
        Song(idx=i, band=f"b{i % 4}", song=f"s{i}", video_id=f"vid{i:08d}",
             camelot=f"{(i % 12) + 1}A", energy=i / n, mode_score=0.0,
             shape="neutral", eligible_band=True)
        for i in range(n)
    ]


def test_stage_boundary_energy_flows_smoothly_not_stepwise():
    # 3단계 상승 아크(0.2→0.8)에서, 스테이지0 경계 근처 곡은 flat 목표(0.2)만 봤다면 절대
    # 못 골랐을 더 높은 강도(허용창 밖)까지 자연스럽게 포함되어야 한다 — 계단식이 아니라는 증거.
    pool = _fine_grained_pool(50)
    params = MoodParameters(brightness=0.0, start_energy=0.2, end_energy=0.8, stage_count=3,
                            target_minutes=None, interpretation_summary="")
    setlist = build_setlist(pool, params, target_seconds=12 * 213, rng=random.Random(0))
    stage0_energies = [p.energy for p in setlist.picks if p.stage_index == 0]
    stage2_energies = [p.energy for p in setlist.picks if p.stage_index == 2]
    # flat target(0.2) ± 허용창(0.08)이면 stage0은 0.28을 못 넘는다 — 보간 덕에 넘을 수 있다.
    assert max(stage0_energies) > 0.28
    # 반대쪽 끝(stage2, flat target 0.8)도 대칭적으로 허용창 아래(0.72)까지 내려올 수 있다.
    assert min(stage2_energies) < 0.72
    # 스테이지 보고값(그래프용) 자체는 여전히 flat 그대로 — API·그래프 호환 유지.
    assert [s.energy_target for s in setlist.stages] == pytest.approx([0.2, 0.5, 0.8])


def test_local_refine_order_fixes_forced_bad_placement():
    # 5곡, 하모닉·경계텐션 전부 동일(intro/outro=0, 같은 camelot)이라 비용은 순수하게
    # "슬롯 목표에서 얼마나 벗어났는가"만 남는다 — 이 경우 정답은 에너지 내림차순 배치.
    songs = [
        Song(idx=i, band="a", song=f"s{i}", video_id=f"vid{i:07d}0", camelot="8A",
             energy=e, mode_score=0.0, shape="neutral", eligible_band=True)
        for i, e in enumerate([0.8, 0.5, 0.1, 0.5, 0.8])
    ]
    bad_order = [songs[2], songs[0], songs[4], songs[1], songs[3]]  # 일부러 강도 순서 무시
    slot_targets = [0.8, 0.65, 0.5, 0.35, 0.1]  # 하강 아크
    improved = _local_refine_order(bad_order, slot_targets)
    assert _stage_sequence_cost(improved, slot_targets) <= _stage_sequence_cost(bad_order, slot_targets)
    assert [s.energy for s in improved] == [0.8, 0.8, 0.5, 0.5, 0.1]


def test_manual_v_shape_arc_has_bounded_reversal():
    # 실사용 재현(수동 배치 [0.8, 0.10, 0.80]): Stage A가 슬롯별로 부드럽게 골라도 Stage B가
    # 순서를 다시 섞으면 경계에서 크게 튈 수 있었다(버그) — 이제 인접 곡 간 에너지 역전폭이
    # 크게 벌어지지 않아야 한다.
    pool = _fine_grained_pool(60)
    specs = [StageSpec(energy_target=0.8, song_count=5),
             StageSpec(energy_target=0.10, song_count=5),
             StageSpec(energy_target=0.80, song_count=5)]
    params = MoodParameters(brightness=0.0, start_energy=0.8, end_energy=0.8, stage_count=3,
                            target_minutes=None, interpretation_summary="")
    for seed in range(10):
        setlist = build_setlist(pool, params, target_seconds=15 * 213, stage_specs=specs,
                                rng=random.Random(seed))
        energies = [p.energy for p in setlist.picks]
        # 인접 곡 사이의 "역행폭"(하강해야 할 구간에서 갑자기 튀는 정도)이 버그 재현치(0.3+)
        # 만큼 크면 안 된다 — 완벽한 단조는 못 보장해도(이산적 후보 제약) 급반전은 막는다.
        jumps = [abs(b - a) for a, b in zip(energies, energies[1:])]
        assert max(jumps) < 0.3, f"seed={seed} energies={energies}"


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


def test_stage_minutes_skews_song_counts_with_stage_energies():
    # 3.5단계: stage_energies + stage_minutes 조합 — 가운데 단계가 훨씬 길면 곡도 더 많이 배정.
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=3,
        target_minutes=None, interpretation_summary="", stage_energies=[0.2, 0.9, 0.3],
        stage_minutes=[10.0, 40.0, 10.0],
    )
    setlist = build_setlist(_songs(), params, target_seconds=9 * 213, rng=random.Random(0))
    counts = [sum(1 for p in setlist.picks if p.stage_index == i) for i in range(3)]
    assert counts[1] > counts[0]
    assert counts[1] > counts[2]
    assert sum(counts) == len(setlist.picks)


def test_stage_minutes_skews_song_counts_without_stage_energies():
    # stage_energies 없이 start/end 선형 아크만 있어도 stage_minutes는 반영돼야 한다.
    params = MoodParameters(
        brightness=0.0, start_energy=0.2, end_energy=0.9, stage_count=3,
        target_minutes=None, interpretation_summary="", stage_minutes=[5.0, 5.0, 40.0],
    )
    setlist = build_setlist(_songs(), params, target_seconds=9 * 213, rng=random.Random(0))
    counts = [sum(1 for p in setlist.picks if p.stage_index == i) for i in range(3)]
    assert counts[2] > counts[0]
    assert counts[2] > counts[1]


def test_stage_minutes_ignored_when_length_mismatches_stage_count():
    # 배열 길이가 stage_count와 다르면(모델 실수) 신뢰하지 않고 균등분배로 폴백 —
    # stage_minutes가 아예 없을 때와 결과(단계별 곡 수)가 완전히 같아야 한다.
    base_params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=3,
        target_minutes=None, interpretation_summary="", stage_energies=[0.2, 0.9, 0.3],
    )
    mismatched_params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=3,
        target_minutes=None, interpretation_summary="", stage_energies=[0.2, 0.9, 0.3],
        stage_minutes=[10.0, 40.0],  # 길이 2 != stage_count 3
    )
    setlist_base = build_setlist(_songs(), base_params, target_seconds=9 * 213, rng=random.Random(0))
    setlist_mismatched = build_setlist(_songs(), mismatched_params, target_seconds=9 * 213, rng=random.Random(0))
    counts_base = [sum(1 for p in setlist_base.picks if p.stage_index == i) for i in range(3)]
    counts_mismatched = [sum(1 for p in setlist_mismatched.picks if p.stage_index == i) for i in range(3)]
    assert counts_mismatched == counts_base


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


# ── 신규 필드 통과 및 매칭 미반영 회귀 ──────────────────────────────────────────
def test_stage_specs_pass_through_new_fields():
    """StageSpec의 신규 필드(valence 등)가 Stage까지 전달되는지 확인."""
    specs = [
        StageSpec(energy_target=0.3, song_count=2, valence=0.7, lra=5.5),
        StageSpec(energy_target=0.7, song_count=3, valence=0.4, lra=10.2),
    ]
    setlist = build_setlist(_songs(), _params(), target_seconds=999, stage_specs=specs, rng=random.Random(0))
    assert len(setlist.stages) == 2
    assert setlist.stages[0].energy_target == 0.3
    assert setlist.stages[0].valence == 0.7
    assert setlist.stages[0].lra == 5.5
    assert setlist.stages[1].energy_target == 0.7
    assert setlist.stages[1].valence == 0.4
    assert setlist.stages[1].lra == 10.2


def test_ai_mode_stage_params_used_when_no_stage_specs():
    """3단계: stage_specs가 없어도(=AI 모드 첫 요청) params.stage_params가 있으면 Stage에 반영된다."""
    params = MoodParameters(
        brightness=0.3, start_energy=0.2, end_energy=0.9, stage_count=2,
        target_minutes=None, interpretation_summary="test",
        stage_params=[
            {"valence": 0.7, "lra": 5.5},
            {"valence": 0.4, "lra": 10.2},
        ],
    )
    setlist = build_setlist(_songs(), params, target_seconds=999, rng=random.Random(0))
    assert len(setlist.stages) == 2
    assert setlist.stages[0].valence == 0.7
    assert setlist.stages[0].lra == 5.5
    assert setlist.stages[0].danceability_norm is None
    assert setlist.stages[1].valence == 0.4
    assert setlist.stages[1].lra == 10.2


def test_stage_specs_take_priority_over_stage_params():
    """사용자 지정 stage_specs가 있으면 LLM stage_params보다 우선한다(필드별)."""
    specs = [StageSpec(energy_target=0.3, song_count=3, valence=0.9)]
    params = MoodParameters(
        brightness=0.0, start_energy=0.3, end_energy=0.3, stage_count=1,
        target_minutes=None, interpretation_summary="test",
        stage_params=[{"valence": 0.1, "lra": 0.5}],
    )
    setlist = build_setlist(_songs(), params, target_seconds=999, stage_specs=specs, rng=random.Random(0))
    # valence는 spec이 우선(0.9, LLM의 0.1 아님), lra는 spec에 없어 stage_params로 폴백(0.5).
    assert setlist.stages[0].valence == 0.9
    assert setlist.stages[0].lra == 0.5


def test_new_fields_do_not_affect_selection_when_songs_lack_them():
    """3.5단계: 곡 풀에 신규 지표(Song.valence 등)가 없으면(이 파일의 _songs() 픽스처처럼
    전부 None) stage_specs/stage_params에 값을 줘도 거리가 0으로 무력화돼 선곡이 안 바뀐다
    — 기존 스냅샷·테스트 픽스처와의 하위호환. 지표가 실제로 있을 때 선곡에 반영되는지는
    test_stage_params_valence_influences_pick_when_available 참고."""
    # valence가 다르지만 energy_target이 같은 두 개의 specs
    specs_without_valence = [
        StageSpec(energy_target=0.3, song_count=3),
        StageSpec(energy_target=0.7, song_count=3),
    ]
    specs_with_valence = [
        StageSpec(energy_target=0.3, song_count=3, valence=0.9),
        StageSpec(energy_target=0.7, song_count=3, valence=0.1),
    ]
    setlist1 = build_setlist(_songs(), _params(), target_seconds=999, stage_specs=specs_without_valence, rng=random.Random(42))
    setlist2 = build_setlist(_songs(), _params(), target_seconds=999, stage_specs=specs_with_valence, rng=random.Random(42))

    # 선곡 결과(picks의 idx 집합)가 동일해야 함
    picks1 = {p.idx for p in setlist1.picks}
    picks2 = {p.idx for p in setlist2.picks}
    assert picks1 == picks2, "신규 필드의 유무가 선곡 결과를 변경해서는 안 됨"


def test_stage_params_valence_influences_pick_when_available():
    """3.5단계: 곡에 실제 valence 값이 있으면 stage_specs.valence가 Stage A 3순위
    타이브레이커로 반영돼 다른 곡이 뽑힌다(에너지·밝기는 전부 동일하게 맞춰 valence만 변수로)."""
    songs = [
        Song(idx=i, band="a", song=f"s{i}", video_id=f"vid{i:07d}0", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True, valence=v)
        for i, v in enumerate([0.1, 0.3, 0.5, 0.7, 0.9])
    ]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
    )
    spec_low = [StageSpec(energy_target=0.5, song_count=1, valence=0.1)]
    spec_high = [StageSpec(energy_target=0.5, song_count=1, valence=0.9)]
    low = build_setlist(songs, params, target_seconds=999, stage_specs=spec_low, rng=random.Random(0))
    high = build_setlist(songs, params, target_seconds=999, stage_specs=spec_high, rng=random.Random(0))
    picked_low = next(s for s in songs if s.idx == low.picks[0].idx)
    picked_high = next(s for s in songs if s.idx == high.picks[0].idx)
    assert picked_low.idx != picked_high.idx
    assert picked_low.valence < picked_high.valence


def test_stage_params_multi_field_distance_picks_closest_overall():
    """valence·lra 두 지표를 동시에 지정하면 평균 거리가 가장 가까운 곡이 뽑힌다."""
    songs = [
        Song(idx=0, band="a", song="s0", video_id="vid0000000", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True,
             valence=0.2, lra=0.8),  # valence 거리 0.6, lra 거리 0.1 → 평균 0.35
        Song(idx=1, band="a", song="s1", video_id="vid0000001", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True,
             valence=0.75, lra=0.75),  # valence 거리 0.05, lra 거리 0.05 → 평균 0.05
    ]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
    )
    spec = [StageSpec(energy_target=0.5, song_count=1, valence=0.8, lra=0.7)]
    setlist = build_setlist(songs, params, target_seconds=999, stage_specs=spec, rng=random.Random(0))
    assert setlist.picks[0].idx == 1


# ── 가사 감상 임베딩 매칭(프로토타입, 4순위 타이브레이크) ──────────────────────────────

def test_resolve_stage_target_params_includes_impression_from_llm():
    from app.domain.selection import _resolve_stage_target_params
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
        stage_params=[{"valence": 0.5, "impression": "차분하고 그리운 정서"}],
    )
    resolved = _resolve_stage_target_params(0, None, params)
    assert resolved["impression"] == "차분하고 그리운 정서"


def test_resolve_stage_target_params_impression_none_when_no_llm_stage_params():
    from app.domain.selection import _resolve_stage_target_params
    params = _params(stage_count=1)
    resolved = _resolve_stage_target_params(0, None, params)
    assert resolved["impression"] is None


def test_resolve_stage_impression_text_spec_takes_priority_over_llm():
    """커스텀 모드(StageSpec.impression) 사용자 입력이 AI 모드 LLM stage_params보다 우선한다."""
    from app.domain.selection import resolve_stage_impression_text
    specs = [StageSpec(energy_target=0.5, song_count=1, impression="사용자 직접 입력")]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
        stage_params=[{"impression": "LLM이 뽑은 감상"}],
    )
    assert resolve_stage_impression_text(0, specs, params) == "사용자 직접 입력"


def test_resolve_stage_impression_text_falls_back_to_llm_when_spec_has_none():
    from app.domain.selection import resolve_stage_impression_text
    specs = [StageSpec(energy_target=0.5, song_count=1)]  # impression 미지정
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
        stage_params=[{"impression": "LLM이 뽑은 감상"}],
    )
    assert resolve_stage_impression_text(0, specs, params) == "LLM이 뽑은 감상"


def test_lyric_similarity_neutral_when_either_side_missing():
    from app.domain.selection import _lyric_similarity
    song = Song(idx=0, band="a", song="s0", video_id="vid0000000", camelot="8A",
                energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True,
                lyric_vec=[1.0, 0.0])
    song_no_vec = Song(idx=1, band="a", song="s1", video_id="vid0000001", camelot="8A",
                        energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True)
    assert _lyric_similarity(song, None) == 0.0
    assert _lyric_similarity(song_no_vec, [1.0, 0.0]) == 0.0
    assert _lyric_similarity(song, [1.0, 0.0]) == 1.0
    assert _lyric_similarity(song, [0.0, 1.0]) == 0.0


def test_build_setlist_lyric_similarity_breaks_tie_when_numeric_params_equal():
    """energy·밝기·6개 수치 지표가 모두 동률인 두 후보 중 1곡만 뽑아야 하는 상황에서,
    가사 감상 임베딩이 더 유사한 쪽이 선택돼야 한다(4순위 타이브레이크, 프로토타입).
    target_seconds를 곡 1개분(avg_song_seconds)으로 맞춰 후보 2곡 중 1곡만 채택되게 한다
    — 그래야 Stage A의 선택 자체(둘 다 채택되는 게 아니라)가 검증된다."""
    songs = [
        Song(idx=0, band="a", song="s0", video_id="vid0000000", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True,
             lyric_vec=[0.0, 1.0]),  # target과 직교(유사도 0)
        Song(idx=1, band="a", song="s1", video_id="vid0000001", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True,
             lyric_vec=[1.0, 0.0]),  # target과 완전 일치(유사도 1)
    ]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
    )
    setlist = build_setlist(
        songs, params, target_seconds=213, rng=random.Random(0),
        stage_impression_vectors=[[1.0, 0.0]],
    )
    assert len(setlist.picks) == 1
    assert setlist.picks[0].idx == 1


def test_build_setlist_missing_impression_vector_keeps_existing_behavior():
    """스테이지 impression 벡터가 없으면(프로토타입 신호 부재) 기존 동작 그대로 —
    가사 유사도 타이브레이크가 결과에 영향을 주지 않는다(크래시도 안 남)."""
    songs = [
        Song(idx=i, band="a", song=f"s{i}", video_id=f"vid{i:07d}0", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True)
        for i in range(3)
    ]
    params = _params(stage_count=1, start=0.5, end=0.5)
    setlist = build_setlist(songs, params, target_seconds=999, rng=random.Random(0))
    assert len(setlist.picks) >= 1


# ── 스테이지별 고정 밴드(프로토타입) ────────────────────────────────────────────

def test_resolve_stage_band_spec_takes_priority_over_llm():
    specs = [StageSpec(energy_target=0.5, song_count=1, band="roselia")]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
        stage_bands=["mygo"],
    )
    assert resolve_stage_band(0, specs, params) == "roselia"


def test_resolve_stage_band_falls_back_to_llm_when_spec_has_none():
    specs = [StageSpec(energy_target=0.5, song_count=1)]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
        stage_bands=["mygo"],
    )
    assert resolve_stage_band(0, specs, params) == "mygo"


def test_resolve_stage_band_none_when_neither_set():
    assert resolve_stage_band(0, None, _params(stage_count=1)) is None


def test_build_setlist_stage_bands_hard_filters_per_stage():
    """두 밴드가 섞인 풀에서 stage_bands로 스테이지별 밴드를 고정하면, 각 스테이지는
    오직 그 밴드 곡만 뽑는다(에너지 하드필터보다 우선하는 최상위 필터)."""
    songs = [
        Song(idx=i, band="morfonica", song=f"morf{i}", video_id=f"vidm{i:06d}", camelot="8A",
             energy=e, mode_score=0.0, shape="neutral", eligible_band=True)
        for i, e in enumerate([0.2, 0.3, 0.7, 0.8])
    ] + [
        Song(idx=100 + i, band="mugendai_mutype", song=f"mm{i}", video_id=f"vidu{i:06d}", camelot="8A",
             energy=e, mode_score=0.0, shape="neutral", eligible_band=True)
        for i, e in enumerate([0.2, 0.3, 0.7, 0.8])
    ]
    params = MoodParameters(
        brightness=0.0, start_energy=0.25, end_energy=0.75, stage_count=2,
        target_minutes=None, interpretation_summary="test",
        stage_energies=[0.25, 0.75],
        stage_bands=["morfonica", "mugendai_mutype"],
    )
    setlist = build_setlist(songs, params, target_seconds=2 * 213, rng=random.Random(0))
    by_idx = {s.idx: s for s in songs}
    stage0_bands = {by_idx[p.idx].band for p in setlist.picks if p.stage_index == 0}
    stage1_bands = {by_idx[p.idx].band for p in setlist.picks if p.stage_index == 1}
    assert stage0_bands == {"morfonica"}
    assert stage1_bands == {"mugendai_mutype"}


def test_build_setlist_stage_band_skips_slot_when_band_pool_exhausted():
    """지정된 밴드의 후보가 소진되면(곡 부족), 억지로 다른 밴드를 채우지 않고 슬롯을
    건너뛴다 — 곡 수가 자동으로 줄어든다."""
    songs = [
        Song(idx=0, band="morfonica", song="only", video_id="vidm0000000", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True),
    ] + [
        Song(idx=100 + i, band="mygo", song=f"mygo{i}", video_id=f"vidg{i:06d}", camelot="8A",
             energy=0.5, mode_score=0.0, shape="neutral", eligible_band=True)
        for i in range(5)
    ]
    params = MoodParameters(
        brightness=0.0, start_energy=0.5, end_energy=0.5, stage_count=1,
        target_minutes=None, interpretation_summary="test",
        stage_bands=["morfonica"],
    )
    # 3곡 분량을 요청해도 morfonica 후보가 1곡뿐이라 1곡만 채택돼야 한다(mygo로 채우지 않음).
    setlist = build_setlist(songs, params, target_seconds=3 * 213, rng=random.Random(0))
    assert len(setlist.picks) == 1
    assert setlist.picks[0].idx == 0
