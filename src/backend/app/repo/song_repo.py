"""songs_master.csv 로더 → list[Song].

데이터팀 산출물 `data/songs_master.csv`를 읽기 전용으로 소비한다(코드팀은 CSV 편집 금지).
video_id는 CSV 컬럼을 신뢰하되, 비어 있으면 `src/scripts/data/video_id.py`(cross-team,
읽기 전용)로 url에서 추출한다.
"""

from __future__ import annotations

import bisect
import csv
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from ..domain.models import Song
from .ja_transliteration import to_hangul, to_hangul_variants, to_hanja_reading, to_romaji

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
DEFAULT_LYRIC_JSON_PATH = _REPO_ROOT / "data" / "lyric_impressions.json"
DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent / "song_alias_overrides.json"


def _resolve_path(csv_path: str | os.PathLike[str] | None) -> Path:
    if csv_path is not None:
        return Path(csv_path)
    env_path = os.environ.get("SONGS_CSV")
    return Path(env_path) if env_path else DEFAULT_CSV_PATH


def _resolve_lyric_path(lyric_json_path: str | os.PathLike[str] | None) -> Path:
    if lyric_json_path is not None:
        return Path(lyric_json_path)
    env_path = os.environ.get("LYRIC_EMBEDDINGS_JSON")
    return Path(env_path) if env_path else DEFAULT_LYRIC_JSON_PATH


def _load_lyric_map(path: Path) -> dict[tuple[str, str], list[float]]:
    """가사 감상 임베딩 자산 로드 — 없으면(프로토타입 자산이라 필수 아님) 빈 딕셔너리.

    `data/lyric_impressions.json`: `{"band|||song": {"desc": str, "vec": [floats]}}`.
    """
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}
    out: dict[tuple[str, str], list[float]] = {}
    for key, entry in raw.items():
        band, _, song = key.partition("|||")
        vec = entry.get("vec")
        if band and song and vec:
            out[(band, song)] = vec
    return out


def _load_overrides() -> dict[str, dict[str, str]]:
    """song_alias_overrides.json 로드(없거나 비어 있으면 빈 딕셔너리 반환)."""
    try:
        if DEFAULT_OVERRIDES_PATH.exists():
            with DEFAULT_OVERRIDES_PATH.open(encoding="utf-8") as f:
                return json.load(f) or {}
    except (json.JSONDecodeError, IOError):
        pass
    return {}


# 오디오 지표 6종 — Song 필드명 → songs_master.csv 컬럼명(데이터팀 m*-prefix 유지).
AUDIO_FEATURE_COLS = {
    "valence": "m6-valence_median",
    "lufs_integrated": "m4-lufs_integrated",
    "lra": "m4-lra",
    "danceability_norm": "m7-danceability_norm",
    "instr_stem_ratio": "m9-instr_stem_ratio",
    "speech_median": "m11-speech_median",
}


def _minmax_scalers(rows: list[dict[str, str]]) -> dict[str, Callable[[float], float]]:
    """지표별 minmax 스케일 함수(eligible 풀 기준, 0~1 클램프). 컬럼이 없으면 그 지표는 생략."""
    scalers: dict[str, Callable[[float], float]] = {}
    for field, col in AUDIO_FEATURE_COLS.items():
        values = [float(r[col]) for r in rows if (r.get(col) or "").strip()]
        if not values:
            continue
        lo, hi = min(values), max(values)
        span = hi - lo
        scalers[field] = (lambda v, lo=lo, span=span:
                          0.5 if span == 0 else max(0.0, min(1.0, (v - lo) / span)))
    return scalers


def _to_song(row: dict[str, str], energy: float, overrides: dict[str, dict[str, str]] | None = None,
             scalers: dict[str, Callable[[float], float]] | None = None,
             lyric_map: dict[tuple[str, str], list[float]] | None = None) -> Song:
    url = (row.get("url") or "").strip()
    video_id = (row.get("video_id") or "").strip()
    if not video_id:
        video_id = extract_video_id(url)

    duration_raw = (row.get("duration_sec") or "").strip()
    duration_sec = int(duration_raw) if duration_raw else None

    intro_raw = (row.get("i_start") or "").strip()
    outro_raw = (row.get("i_end") or "").strip()

    song_title = row["song"]
    # 오버라이드 키: songs_master.csv엔 tag 컬럼이 없다(연구용 CSV 전용 컬럼) — 곡을 유일하게
    # 식별하는 idx를 문자열로 써서 song_alias_overrides.json과 매칭한다.
    idx_key = (row.get("idx") or "").strip()

    # 검색 보조 필드 자동 계산
    song_romaji = to_romaji(song_title)
    song_hangul = to_hangul(song_title)
    song_hangul_variants = to_hangul_variants(song_title)
    song_hanja_reading = to_hanja_reading(song_title)

    # 오버라이드 적용 (부분 오버라이드 허용 — 지정된 필드만 대체)
    if overrides and idx_key and idx_key in overrides:
        override_data = overrides[idx_key]
        if "song_romaji" in override_data:
            song_romaji = override_data["song_romaji"]
        if "song_hangul" in override_data:
            song_hangul = override_data["song_hangul"]
        if "song_hanja_reading" in override_data:
            song_hanja_reading = override_data["song_hanja_reading"]

    # 검색 매칭용 병기 문자열 — 오버라이드된 song_hangul(수동 관용 표기)도 항상 포함한다.
    song_hangul_search = " / ".join(dict.fromkeys([song_hangul, *song_hangul_variants]))

    # 오디오 지표 6종(minmax 스케일). 셀이 비었거나 컬럼/스케일러가 없으면 None 유지.
    audio_feats: dict[str, float | None] = {}
    for field, col in AUDIO_FEATURE_COLS.items():
        raw = (row.get(col) or "").strip()
        scaler = (scalers or {}).get(field)
        audio_feats[field] = scaler(float(raw)) if raw and scaler else None

    lyric_vec = (lyric_map or {}).get((row["band"], song_title))

    return Song(
        **audio_feats,
        idx=int(row["idx"]),
        band=row["band"],
        song=song_title,
        video_id=video_id,
        camelot=row["camelot"],
        energy=energy,
        mode_score=float(row["mode_score"]),
        shape=row["shape"],
        eligible_band=str(row["eligible_band"]).strip().lower() == "true",
        duration_sec=duration_sec,
        intro_energy=float(intro_raw) if intro_raw else 0.0,
        outro_energy=float(outro_raw) if outro_raw else 0.0,
        lyric_vec=lyric_vec,
        # 검색 보조 필드(§ja_transliteration) — 서버 기동 시 이 함수 호출 때 1회 계산돼 캐싱됨.
        song_romaji=song_romaji,
        song_hangul=song_hangul,
        song_hangul_search=song_hangul_search,
        song_hanja_reading=song_hanja_reading,
    )


# 강도(intensity) soft-OR power-mean 지수. 여러 독립 신호를 결합(어느 하나라도 시끄러우면 시끄럽게).
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


def load_songs(csv_path: str | os.PathLike[str] | None = None,
                lyric_json_path: str | os.PathLike[str] | None = None) -> list[Song]:
    """songs_master.csv를 읽어 전체 곡 목록을 반환한다.

    eligible 여부와 무관하게 전 행을 적재한다(후보 필터링은 선곡 엔진이 수행).
    `Song.energy`는 무드 **강도(intensity)** — 서로 다른 곡을 잡는 독립 신호들을 soft-OR
    (power-mean p=3)로 결합해 산출한다. "어느 한 신호라도 시끄럽다면 시끄럽게" 본다.

    데이터 검증(2026-07-11) 및 전곡 재추출 보고서:
    - `energy`(EMOI-MAP 펄스용)·`energy_proxy`·`acousticness_proxy`는 발췌 구간만 반영 → 오판.
    - 데이터팀이 로컬 전곡 오디오에서 재추출한 두 신호를 사용:
      · `energy_full`(전곡 지각에너지 복합, 0~1) — party/rock 곡을 잡음.
      · 시간분절 강도 `i_mean`·`i_min`·`i_end`(전곡 프레임별 강도 시계열의 통계) — 특히 `i_min`은
        "한 번도 조용해지지 않는" 곡(Steer to Utopia 등)을, `i_end`는 조용한 인트로+시끄러운
        본체 곡을 잡는다(`src/scripts/data/extract_temporal_intensity.py`).
    - 결합 신호: [`energy_full`, `−acousticness_proxy` 백분위(헤비메탈 黒 등), `i_min`·`i_mean`·
      `i_end` 백분위]. 결측 컬럼은 자동 제외. (근거: document-archive 브랜치 `archive/last-papers/research/2026-07-11-*.md`.)

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
    rank_acoustic = _percentile_ranker([-float(r["acousticness_proxy"]) for r in eligible])
    # 시간분절 신호(있을 때만). i_min=가장 조용한 순간, i_end=아웃트로, i_mean=전곡 평균.
    _temporal = ("i_min", "i_mean", "i_end")
    rankers = {
        col: _percentile_ranker([float(r[col]) for r in eligible if (r.get(col) or "").strip()])
        for col in _temporal
        if any((r.get(col) or "").strip() for r in eligible)
    }
    p = _INTENSITY_P

    def intensity(row: dict[str, str]) -> float:
        signals = [rank_acoustic(-float(row["acousticness_proxy"]))]  # 1=가장 비어쿠스틱(시끄러움)
        ef_raw = (row.get("energy_full") or "").strip()
        if ef_raw:
            signals.append(float(ef_raw))  # 전곡 에너지(0~1)
        for col, ranker in rankers.items():
            v = (row.get(col) or "").strip()
            if v:
                signals.append(ranker(float(v)))
        return (sum(s ** p for s in signals) / len(signals)) ** (1.0 / p)

    # 오버라이드 로드 (매 서버 시작 시 1회 — 빈 딕셔너리로 폴백 가능)
    overrides = _load_overrides()

    # 오디오 지표 6종 minmax 스케일러(백분위와 동일하게 eligible 풀 기준 — 밴드 필터와 무관하게 안정).
    scalers = _minmax_scalers(eligible)

    # 가사 감상 임베딩(프로토타입, 선택) — 자산이 없어도 song_repo는 정상 동작(lyric_vec=None).
    lyric_map = _load_lyric_map(_resolve_lyric_path(lyric_json_path))

    return [_to_song(r, intensity(r), overrides, scalers, lyric_map) for r in rows]
