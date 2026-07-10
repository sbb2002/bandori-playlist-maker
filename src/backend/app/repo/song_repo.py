"""songs_master.csv 로더 → list[Song].

데이터팀 산출물 `data/songs_master.csv`를 읽기 전용으로 소비한다(코드팀은 CSV 편집 금지).
video_id는 CSV 컬럼을 신뢰하되, 비어 있으면 `src/scripts/data/video_id.py`(cross-team,
읽기 전용)로 url에서 추출한다.
"""

from __future__ import annotations

import bisect
import csv
import os
import sys
from collections.abc import Callable
from pathlib import Path

from ..domain.models import Song

# cross-team import(허용): video_id 추출 헬퍼. 경로 삽입 후 import.
#   song_repo.py: .../src/backend/app/repo/song_repo.py → parents[3] == .../src
_SRC_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DATA = _SRC_ROOT / "scripts" / "data"
if str(_SCRIPTS_DATA) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DATA))

from video_id import extract_video_id  # noqa: E402  (cross-team, 경로 삽입 후 import)

# 기본 데이터 경로: 리포지토리 루트 data/songs_master.csv. env로 override 가능.
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CSV_PATH = _REPO_ROOT / "data" / "songs_master.csv"


def _resolve_path(csv_path: str | os.PathLike[str] | None) -> Path:
    if csv_path is not None:
        return Path(csv_path)
    env_path = os.environ.get("SONGS_CSV")
    return Path(env_path) if env_path else DEFAULT_CSV_PATH


def _to_song(row: dict[str, str], energy: float) -> Song:
    url = (row.get("url") or "").strip()
    video_id = (row.get("video_id") or "").strip()
    if not video_id:
        video_id = extract_video_id(url)

    duration_raw = (row.get("duration_sec") or "").strip()
    duration_sec = int(duration_raw) if duration_raw else None

    return Song(
        idx=int(row["idx"]),
        band=row["band"],
        song=row["song"],
        video_id=video_id,
        camelot=row["camelot"],
        energy=energy,
        mode_score=float(row["mode_score"]),
        shape=row["shape"],
        eligible_band=str(row["eligible_band"]).strip().lower() == "true",
        duration_sec=duration_sec,
    )


# 강도(intensity) power-mean 지수(soft-OR). 클수록 보수적(누출↓), 작을수록 다양성↑.
# R&D 보고서(docs/research/2026-07-11-playlist-sequencing-strategy.md §2-i, §3.1) 권장 p=3.
_INTENSITY_P = 3


def _percentile_ranker(values: list[float]) -> Callable[[float], float]:
    """분포(values)에 대한 백분위 순위 함수를 만든다.

    rank(v) = (엄격히 작은 수 + 0.5·동점 수) / n  ∈ [0,1]. min-max의 '중앙 밀집'을 없애
    분포를 균등화한다(목표 0.15가 진짜 하위 15% 곡을 가리키게 됨).
    """
    srt = sorted(values)
    n = len(srt)

    def rank(v: float) -> float:
        if n == 0:
            return 0.5
        less = bisect.bisect_left(srt, v)
        equal = bisect.bisect_right(srt, v) - less
        return (less + 0.5 * equal) / n

    return rank


def load_songs(csv_path: str | os.PathLike[str] | None = None) -> list[Song]:
    """songs_master.csv를 읽어 전체 곡 목록을 반환한다.

    eligible 여부와 무관하게 전 행을 적재한다(후보 필터링은 선곡 엔진이 수행).
    `Song.energy`는 무드 **강도(intensity)** — eligible 풀 기준 백분위 + power-mean(p=3)로 산출.

    데이터 검증(2026-07-11) 및 R&D 시퀀싱 전략 보고서(§2-i):
    - `energy` 컬럼(EMOI-MAP 펄스용)은 무드와 무관/역전 → 폐기.
    - `energy_proxy`(부호반전)·`acousticness_proxy`를 각각 백분위 변환 후, 어느 한쪽이라도
      '시끄럽다'면 시끄럽게 보는 soft-OR(power-mean p=3)로 결합. 발췌 편향(인트로만 조용한
      헤비메탈 등)을 완화한다. 근본 해결은 전곡 재추출(기기 B, 보고서 §5).

    Raises:
        FileNotFoundError: CSV가 없는 경우.
    """
    path = _resolve_path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"songs_master.csv를 찾을 수 없습니다: {path}")

    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # 백분위는 후보가 되는 eligible 풀 분포 기준(밴드 필터와 무관하게 안정).
    eligible = [r for r in rows if str(r["eligible_band"]).strip().lower() == "true"]
    rank_energy = _percentile_ranker([-float(r["energy_proxy"]) for r in eligible])
    rank_acoustic = _percentile_ranker([-float(r["acousticness_proxy"]) for r in eligible])
    p = _INTENSITY_P

    def intensity(row: dict[str, str]) -> float:
        pe = rank_energy(-float(row["energy_proxy"]))       # 1=가장 시끄러움
        pa = rank_acoustic(-float(row["acousticness_proxy"]))  # 1=가장 비어쿠스틱
        return ((pe ** p + pa ** p) / 2.0) ** (1.0 / p)

    return [_to_song(r, intensity(r)) for r in rows]
