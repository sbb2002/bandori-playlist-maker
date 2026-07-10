"""songs_master.csv 로더 → list[Song].

데이터팀 산출물 `data/songs_master.csv`를 읽기 전용으로 소비한다(코드팀은 CSV 편집 금지).
video_id는 CSV 컬럼을 신뢰하되, 비어 있으면 `src/scripts/data/video_id.py`(cross-team,
읽기 전용)로 url에서 추출한다.
"""

from __future__ import annotations

import csv
import os
import sys
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


# energy_proxy 비중(나머지는 acousticness_proxy). 데이터 검증(2026-07-11)으로 선정.
_ENERGY_PROXY_WEIGHT = 0.6


def _norm(value: float, lo: float, hi: float) -> float:
    return (value - lo) / (hi - lo) if hi > lo else 0.5


def _blended_energy(
    energy_proxy: float, acous_proxy: float,
    ep_lo: float, ep_hi: float, ac_lo: float, ac_hi: float,
) -> float:
    """0~1 무드 에너지를 `energy_proxy` + `acousticness_proxy` 블렌드로 산출한다.

    데이터 검증(2026-07-11):
    - 원래 쓰던 `energy` 컬럼(audio_map, EMOI-MAP 펄스용)은 무드 에너지와 무관/역전
      (FIRE BIRD=0.005·栞=0.907, corr 0.24) → 폐기.
    - `energy_proxy`는 올바른 신호이나 **부호 반전**(음수=고에너지). 다만 발췌 구간만 반영해
      인트로만 조용한 곡(예: 黒のバースデイ=헤비메탈)을 조용하다고 오판.
    - `acousticness_proxy`가 진짜 조용/어쿠스틱 곡을 강하게 구분(栞 5.05 vs 黒 -1.37).
    양쪽 모두 반전·정규화 후 가중 평균한다(어쿠스틱↑ → 에너지↓).
    """
    e = _norm(-energy_proxy, -ep_hi, -ep_lo)
    a = _norm(-acous_proxy, -ac_hi, -ac_lo)
    return _ENERGY_PROXY_WEIGHT * e + (1.0 - _ENERGY_PROXY_WEIGHT) * a


def load_songs(csv_path: str | os.PathLike[str] | None = None) -> list[Song]:
    """songs_master.csv를 읽어 전체 곡 목록을 반환한다.

    eligible 여부와 무관하게 전 행을 적재한다(후보 필터링은 선곡 엔진이 수행).
    energy는 `energy_proxy`+`acousticness_proxy` 블렌드로 산출한다(위 `_blended_energy`).

    Raises:
        FileNotFoundError: CSV가 없는 경우.
    """
    path = _resolve_path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"songs_master.csv를 찾을 수 없습니다: {path}")

    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    eps = [float(r["energy_proxy"]) for r in rows]
    acs = [float(r["acousticness_proxy"]) for r in rows]
    ep_lo, ep_hi = min(eps), max(eps)
    ac_lo, ac_hi = min(acs), max(acs)
    return [
        _to_song(r, _blended_energy(float(r["energy_proxy"]), float(r["acousticness_proxy"]),
                                    ep_lo, ep_hi, ac_lo, ac_hi))
        for r in rows
    ]
