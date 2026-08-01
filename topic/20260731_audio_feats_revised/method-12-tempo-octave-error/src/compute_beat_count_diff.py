"""m1-beat_count가 4분음표 기준이라는 가정 하에, duration_sec x bpm_madmom / 60으로
'기대 beat_count'를 역산하고, 실측 beat_count와의 차이(diff_beat_count)를 계산한다.

data/all_features.csv는 건드리지 않는다 — method-12 폴더 안에만 복사본을 만든다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_METHOD12_DIR = Path(__file__).resolve().parent.parent
_TOPIC_DIR = _METHOD12_DIR.parent
_ALL_FEATURES_CSV = _TOPIC_DIR / "data" / "all_features.csv"
_OUT_CSV = _METHOD12_DIR / "out" / "csv" / "beat_count_diff.csv"


def main() -> None:
    df = pd.read_csv(_ALL_FEATURES_CSV)  # 원본 읽기 전용

    out = df[["idx", "band", "song", "m1-duration_sec", "m1-bpm_madmom", "m1-beat_count"]].copy()
    out["expected_beat_count"] = out["m1-duration_sec"] * out["m1-bpm_madmom"] / 60.0
    out["diff_beat_count"] = out["m1-beat_count"] - out["expected_beat_count"]
    out["abs_diff_beat_count"] = out["diff_beat_count"].abs()

    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(_OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"저장: {_OUT_CSV} shape={out.shape}")

    print()
    print("=== diff_beat_count 기술통계 ===")
    print(out["diff_beat_count"].describe())

    print()
    print("=== abs_diff_beat_count 상위 10곡(가장 어긋난 곡) ===")
    top = out.sort_values("abs_diff_beat_count", ascending=False).head(10)
    print(top[["idx", "band", "song", "m1-duration_sec", "m1-bpm_madmom",
               "m1-beat_count", "expected_beat_count", "diff_beat_count"]].to_string(index=False))


if __name__ == "__main__":
    main()
