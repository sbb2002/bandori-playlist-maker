"""오디오 지표 6종 분포 통계 파이프라인 테스트.

song_repo의 minmax 스케일러 → routes의 밴드별 통계 → prompt의 [지표 분포 통계] 블록 주입까지,
LLM이 stage_params를 분포에 근거해 고르게 하는 경로의 순수 함수들을 검증한다.
"""

from backend.app.adapters.prompt import build_messages
from backend.app.api.routes import _feature_stats
from backend.app.domain.models import Song
from backend.app.repo.song_repo import _minmax_scalers


def _song(idx: int, band: str, **feats) -> Song:
    return Song(
        idx=idx, band=band, song=f"s{idx}", video_id="v", camelot="8B",
        energy=0.5, mode_score=0.5, shape="flat", eligible_band=True, **feats,
    )


def test_minmax_scalers_scale_and_clamp():
    rows = [
        {"m4-lufs_integrated": "-20.0", "m4-lra": "4.0"},
        {"m4-lufs_integrated": "-10.0", "m4-lra": "8.0"},
    ]
    scalers = _minmax_scalers(rows)
    assert scalers["lufs_integrated"](-20.0) == 0.0
    assert scalers["lufs_integrated"](-10.0) == 1.0
    assert scalers["lufs_integrated"](-15.0) == 0.5
    # eligible 풀 밖 값(범위 초과)은 0~1로 클램프
    assert scalers["lufs_integrated"](-30.0) == 0.0
    assert scalers["lufs_integrated"](0.0) == 1.0
    # 값이 있는 컬럼만 스케일러 생성
    assert "valence" not in scalers


def test_feature_stats_groups_by_band_with_total():
    pool = [
        _song(1, "Roselia", valence=0.2, lra=0.8),
        _song(2, "Roselia", valence=0.4),
        _song(3, "MyGO!!!!!", valence=0.9),
    ]
    stats = _feature_stats(pool)
    assert set(stats) == {"전체", "Roselia", "MyGO!!!!!"}
    total_v = stats["전체"]["valence"]
    assert total_v["min"] == 0.2 and total_v["max"] == 0.9 and total_v["median"] == 0.4
    assert round(total_v["mean"], 4) == 0.5
    # None 값은 통계에서 제외(lra는 1곡만 보유)
    assert stats["전체"]["lra"]["std"] == 0.0
    # 전 지표 None이면 통계 자체가 None
    assert _feature_stats([_song(4, "Afterglow")]) is None


def test_build_messages_injects_stats_block():
    stats = {"전체": {"valence": {"min": 0.0, "max": 1.0, "mean": 0.5, "median": 0.52, "std": 0.2}}}
    system = build_messages("신나는 한 시간", feature_stats=stats)[0]["content"]
    assert "지표=min/max/mean/median/std" in system  # 블록 헤더(SYSTEM_PROMPT 본문에는 없는 문자열)
    assert "전체: valence=0.00/1.00/0.50/0.52/0.20" in system
    # 통계 없으면 블록도 없음
    assert "지표=min/max/mean/median/std" not in build_messages("신나는 한 시간")[0]["content"]
