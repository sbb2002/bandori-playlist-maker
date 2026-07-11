"""통합 회귀 가드 — 실제 songs_master.csv를 로드해 2단계 엔진의 핵심 속성을 고정한다.

R&D 보고서(docs/research/2026-07-11-playlist-sequencing-strategy.md §4.2)의 가드 지표:
조용 요청에서 무드 누출 없음 + 인접 전환 매끄러움.
"""

import random

from app.domain.models import MoodParameters
from app.domain.selection import build_setlist
from app.repo.song_repo import load_songs


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


def test_seed_reproducible_on_real_data():
    songs = load_songs()
    params = _quiet_params()
    a = build_setlist(songs, params, target_seconds=60 * 60, rng=random.Random(7))
    b = build_setlist(songs, params, target_seconds=60 * 60, rng=random.Random(7))
    assert [p.idx for p in a.picks] == [p.idx for p in b.picks]
