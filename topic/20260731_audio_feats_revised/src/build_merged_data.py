"""method-1~11의 raw csv를 idx 기준으로 전부 병합해 data/all_features.csv를 만든다.

`idx`를 제외한 모든 컬럼은 어느 method에서 왔는지 한눈에 알 수 있도록 `m<N>-<원래컬럼명>`
형태로 접두사를 붙인다(예: `bpm_madmom` → `m1-bpm_madmom`). band/song/duration_sec/error/
extract_sec/n_patches처럼 여러 method에 동일한 이름으로 존재하는 컬럼도 값이 method마다
미세하게 다르거나(duration_sec) 실패 원인이 다를 수 있어(error) 병합하지 않고 각각
`m<N>-band`처럼 그대로 보존한다. 대표로 노출하는 `band`/`song`(접두사 없음)은
method-1-tempo(736곡 전수 기준) 값을 canonical로 채택한 것이다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_TOPIC_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _TOPIC_DIR / "data"

# (method 번호, csv 경로) — 번호가 컬럼 접두사(m<N>-)로 그대로 쓰임
SOURCES = [
    (1, _TOPIC_DIR / "method-1-tempo" / "out" / "csv" / "tempo_raw.csv"),
    (2, _TOPIC_DIR / "method-2-key" / "out" / "csv" / "key_raw.csv"),
    (3, _TOPIC_DIR / "method-3-mode" / "out" / "csv" / "mode_raw.csv"),
    (4, _TOPIC_DIR / "method-4-loudness" / "out" / "csv" / "loudness_raw.csv"),
    (5, _TOPIC_DIR / "method-5-energy" / "out" / "csv" / "energy_raw.csv"),
    (6, _TOPIC_DIR / "method-6-valence" / "out" / "csv" / "valence_raw.csv"),
    (7, _TOPIC_DIR / "method-7-danceability" / "out" / "csv" / "danceability_raw.csv"),
    (8, _TOPIC_DIR / "method-8-acousticness" / "out" / "csv" / "acousticness_raw.csv"),
    (9, _TOPIC_DIR / "method-9-instrumentalness" / "out" / "csv" / "instrumentalness_raw.csv"),
    (10, _TOPIC_DIR / "method-10-liveness" / "out" / "csv" / "liveness_raw.csv"),
    (11, _TOPIC_DIR / "method-11-speechiness" / "out" / "csv" / "speechiness_raw.csv"),
]


def _load(n: int, path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    # idx 중복 행 제거(loudness_raw.csv에 idx=3 완전동일 중복 1건 존재 확인됨)
    df = df.drop_duplicates(subset="idx", keep="first")
    rename = {c: f"m{n}-{c}" for c in df.columns if c != "idx"}
    return df.rename(columns=rename)


def main() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    merged: pd.DataFrame | None = None
    for n, path in SOURCES:
        df = _load(n, path)
        merged = df if merged is None else merged.merge(df, on="idx", how="outer")

    assert merged is not None

    # canonical band/song = tempo 기준(736곡 전수, method-1) — 접두사 없이 노출
    merged["band"] = merged["m1-band"]
    merged["song"] = merged["m1-song"]

    front = ["idx", "band", "song"]
    other = [c for c in merged.columns if c not in front]
    # m1, m2, ..., m10, m11 순서로 정렬(문자열 정렬 시 m10이 m2보다 앞에 오는 문제 방지)
    def _sort_key(col: str) -> tuple[int, str]:
        n = int(col.split("-", 1)[0][1:])
        return (n, col)

    other = sorted(other, key=_sort_key)
    merged = merged[front + other]
    merged = merged.sort_values("idx").reset_index(drop=True)

    out_csv = _DATA_DIR / "all_features.csv"
    merged.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"저장: {out_csv} (shape={merged.shape})")


if __name__ == "__main__":
    main()
