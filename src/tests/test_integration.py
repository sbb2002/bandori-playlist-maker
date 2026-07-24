"""통합 회귀 가드 — songs_master.csv 스냅샷을 로드해 2단계 엔진의 핵심 속성을 고정한다.

R&D 보고서(document-archive 브랜치 archive/last-papers/research/2026-07-11-playlist-sequencing-strategy.md §4.2)의 가드 지표:
조용 요청에서 무드 누출 없음 + 인접 전환 매끄러움.

`main`엔 더 이상 `data/`가 없다(배포된 backend는 런타임에 `data` 브랜치를 원격 fetch —
`app.repo.remote_source` 참조). 이 회귀 가드는 실시간 데이터가 아니라 `fixtures/songs_master.csv`
(코드/테스트팀 소유 고정 스냅샷, 오토로더가 갱신하지 않음)로 결정론적으로 돈다.
"""

import json
import random
from pathlib import Path

from app.domain.models import MoodParameters
from app.domain.selection import build_setlist
from app.repo import song_repo
from app.repo.song_repo import load_songs as _load_songs_from

_FIXTURE = Path(__file__).parent / "fixtures" / "songs_master.csv"


def load_songs():
    return _load_songs_from(_FIXTURE)


def _quiet_params() -> MoodParameters:
    return MoodParameters(
        brightness=0.1, start_energy=0.15, end_energy=0.15,
        stage_count=3, target_minutes=60, interpretation_summary="",
    )


def test_quiet_request_has_no_energetic_leak():
    """조용 요청: 세트리스트 최고 강도 ≤ 0.25 (중간·고에너지 곡 누출 없음)."""
    songs = load_songs()
    params = _quiet_params()
    for seed in range(5):
        setlist = build_setlist(songs, params, target_seconds=60 * 60, rng=random.Random(seed))
        assert max(p.energy for p in setlist.picks) <= 0.25


def test_quiet_request_is_genuinely_low_intensity():
    """조용 요청: 평균 강도가 충분히 낮다(≤ 0.25)."""
    songs = load_songs()
    setlist = build_setlist(songs, _quiet_params(), target_seconds=60 * 60, rng=random.Random(0))
    avg = sum(p.energy for p in setlist.picks) / len(setlist.picks)
    assert avg <= 0.25


def test_adjacent_intensity_transitions_are_smooth():
    """인접 곡 강도 급변 방지: 최대 점프 ≤ 0.30."""
    songs = load_songs()
    setlist = build_setlist(songs, _quiet_params(), target_seconds=60 * 60, rng=random.Random(0))
    energies = [p.energy for p in setlist.picks]
    max_jump = max(abs(energies[i + 1] - energies[i]) for i in range(len(energies) - 1))
    assert max_jump <= 0.30


def test_formerly_misjudged_loud_songs_now_rate_high():
    """전곡 재추출 후, 과거 발췌 편향으로 조용 오판되던 시끄러운 곡이 조용 밴드 위(≥0.28)에 있어야 한다."""
    by_title = {s.song: s for s in load_songs()}
    for title in ["灼熱 Bonfire!", "ドラマチック", "はいよろこんで", "黒のバースデイ", "FIRE BIRD",
                  "Steer to Utopia", "Re:birth day"]:
        song = next((v for k, v in by_title.items() if k.startswith(title)), None)
        assert song is not None, f"{title} 미발견"
        assert song.energy >= 0.28, f"{song.song} intensity={song.energy:.3f} (조용 밴드에 누출)"


def test_genuinely_quiet_songs_rate_low():
    by_title = {s.song: s for s in load_songs()}
    for title in ["栞", "過惰幻"]:
        song = next((v for k, v in by_title.items() if k.startswith(title) and v.band == "mygo"), None)
        assert song is not None, title
        assert song.energy <= 0.1, f"{song.song} intensity={song.energy:.3f}"


def test_boundary_tension_continuity_is_smooth():
    """곡 경계 텐션 연속성(사용자 §종합): 실제 시퀀싱이 무작위 순서보다 유의미하게 매끄러워야 한다.

    절대 임계값(과거 0.44)은 `song_repo._percentile_ranker()`가 energy를 eligible 풀
    **전체 분포 기준**으로 계산하는 구조 때문에 스냅샷이 바뀔 때마다(오토로더 신곡 반영 등)
    모든 곡의 energy가 미세 재계산되어 흔들린다 — 2026-07-13에 곡 2개 제거만으로 0.40→0.437로
    급변한 적이 있고, 2026-07-24 재검증에서도 무작위 2곡 제거만으로 gap이 최대 +0.16(베이스라인
    대비 60%+) 이동함을 확인했다(원인 규명: document-archive 브랜치
    archive/last-papers/research/2026-07-14-boundary-tension-rng-sensitivity-verified.md).

    그래서 절대값 대신, **같은 스냅샷·같은 곡 구성 안에서** "실제 시퀀싱 결과"를 "그 곡들을
    무작위로 배열했을 때의 기대 gap"과 비교하는 상대 지표로 판정한다 — 스냅샷이 바뀌어도 두
    값이 같은 방향으로 움직여 비율은 안정적이다. 실측(2026-07-24, 정상 스냅샷 + 무작위 2~5곡
    제거 80회 시뮬레이션): 비율은 항상 0.28~0.72, 반면 시퀀싱이 고장 나 무작위 순서와 다름없어지면
    비율이 ~1.0 이상으로 뛴다 — 0.80을 통과 기준으로 삼으면 두 상황을 안정적으로 구분한다.
    """
    import statistics

    def mean_gap(by_idx, order):
        return statistics.mean(
            abs(by_idx[a.idx].outro_energy - by_idx[b.idx].intro_energy)
            for a, b in zip(order, order[1:])
        )

    songs = load_songs()
    by_idx = {s.idx: s for s in songs}
    sl = build_setlist(songs, _quiet_params(), target_seconds=60 * 60, rng=random.Random(0))
    actual_gap = mean_gap(by_idx, sl.picks)

    # 같은 곡 구성을 무작위로 배열했을 때의 기대 gap(몬테카를로 베이스라인, 고정 시드로 결정론적).
    baseline_rng = random.Random(12345)
    shuffled = list(sl.picks)
    baseline_gaps = []
    for _ in range(200):
        baseline_rng.shuffle(shuffled)
        baseline_gaps.append(mean_gap(by_idx, shuffled))
    baseline_gap = statistics.mean(baseline_gaps)

    ratio = actual_gap / baseline_gap
    assert ratio <= 0.80, (
        f"actual={actual_gap:.4f} random_baseline={baseline_gap:.4f} ratio={ratio:.4f} "
        f"(>0.80 — 무작위 순서 대비 개선폭이 부족함)"
    )


def _rising_params() -> MoodParameters:
    return MoodParameters(
        brightness=0.6, start_energy=0.35, end_energy=0.85,
        stage_count=3, target_minutes=60, interpretation_summary="",
    )


def test_rising_arc_direction_is_monotonic():
    """상승 요청: 단계 평균 강도가 단계별 증가(아크 방향 정합, R&D §9 필수 게이트)."""
    songs = load_songs()
    sl = build_setlist(songs, _rising_params(), target_seconds=60 * 60, rng=random.Random(0))
    stage_means = []
    for k in range(3):
        energies = [p.energy for p in sl.picks if p.stage_index == k]
        if energies:
            stage_means.append(sum(energies) / len(energies))
    assert stage_means == sorted(stage_means)


def test_arc_target_adherence():
    """단계별 실제 평균 강도가 단계 목표에 근접(MAE ≤ 0.15, R&D §9 필수 게이트)."""
    songs = load_songs()
    sl = build_setlist(songs, _rising_params(), target_seconds=60 * 60, rng=random.Random(0))
    targets = [s.energy_target for s in sl.stages]
    errors = []
    for k, target in enumerate(targets):
        energies = [p.energy for p in sl.picks if p.stage_index == k]
        if energies:
            errors.append(abs(sum(energies) / len(energies) - target))
    assert sum(errors) / len(errors) <= 0.15


def test_seed_reproducible_on_real_data():
    songs = load_songs()
    params = _quiet_params()
    a = build_setlist(songs, params, target_seconds=60 * 60, rng=random.Random(7))
    b = build_setlist(songs, params, target_seconds=60 * 60, rng=random.Random(7))
    assert [p.idx for p in a.picks] == [p.idx for p in b.picks]


def test_song_alias_override_applies_by_idx(monkeypatch, tmp_path):
    """song_alias_overrides.json은 idx(문자열)로 매칭돼야 한다 — songs_master.csv엔
    tag 컬럼이 없으므로 tag로 매칭하면 항상 무적용(dead code)이 된다는 회귀를 잡는다."""
    overrides_path = tmp_path / "song_alias_overrides.json"
    overrides_path.write_text(
        json.dumps({"0": {"song_hangul": "온 유어 마크(수동 지정)"}}), encoding="utf-8",
    )
    monkeypatch.setattr(song_repo, "DEFAULT_OVERRIDES_PATH", overrides_path)

    songs = load_songs()
    target = next(s for s in songs if s.idx == 0)
    assert target.song_hangul == "온 유어 마크(수동 지정)"

    # 오버라이드 미지정 필드(song_romaji)는 자동 계산값을 그대로 유지해야 한다(부분 오버라이드).
    assert target.song_romaji and target.song_romaji != "온 유어 마크(수동 지정)"
