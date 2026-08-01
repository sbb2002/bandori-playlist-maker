"""tempo(bpm_madmom)를 느낌 기반 4단계 카테고리(slow/medium/fast/boost)로 치환하는 실험.

data/all_features.csv는 건드리지 않는다 — 이 스크립트는 그 파일을 읽어서
method-12 폴더 안에만 복사본(+카테고리 컬럼)을 만든다. 옥타브 오차가 있는 곡은
카테고리 자체가 통째로 바뀔 수 있다는 걸 그대로 보여주는 게 목적(보정 아님).

경계값(연구자 지정):
- slow:   ~90
- medium: 90~160
- fast:   160~210
- boost:  210~
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_METHOD12_DIR = Path(__file__).resolve().parent.parent
_TOPIC_DIR = _METHOD12_DIR.parent
_ALL_FEATURES_CSV = _TOPIC_DIR / "data" / "all_features.csv"
_BESTDORI_CSV = _TOPIC_DIR / "method-1-tempo" / "out" / "csv" / "tempo_bestdori_comparison.csv"

_OUT_CSV = _METHOD12_DIR / "out" / "csv" / "all_features_with_tempo_category.csv"
_OUT_FLIP_CSV = _METHOD12_DIR / "out" / "csv" / "tempo_category_flip_check.csv"

BINS = [0, 90, 160, 210, 10_000]
LABELS = ["slow", "medium", "fast", "boost"]


def categorize(bpm: pd.Series) -> pd.Series:
    return pd.cut(bpm, bins=BINS, labels=LABELS, right=False)


def main() -> None:
    df = pd.read_csv(_ALL_FEATURES_CSV)  # 원본은 읽기만 함, 수정 없음
    df = df.copy()
    df["m1-tempo_category"] = categorize(df["m1-bpm_madmom"])

    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"저장(복사본): {_OUT_CSV} shape={df.shape}")

    print()
    print("=== 전체 736곡 카테고리 분포(m1-bpm_madmom 기준) ===")
    print(df["m1-tempo_category"].value_counts().reindex(LABELS))

    # --- 옥타브 오차 31곡: 카테고리가 실제로 바뀌는지 확인 ---
    bestdori = pd.read_csv(_BESTDORI_CSV)[["idx", "official_bpm", "ratio", "octave_class"]]
    check = bestdori.merge(df[["idx", "m1-bpm_madmom", "m1-tempo_category"]], on="idx", how="left")
    check["official_category"] = categorize(check["official_bpm"])
    check["category_flipped"] = check["m1-tempo_category"] != check["official_category"]

    mismatch = check[~check["ratio"].between(0.92, 1.08)].copy()
    correct = check[check["ratio"].between(0.92, 1.08)].copy()

    print()
    print(f"=== 정답군(n={len(correct)}) 카테고리 우연 불일치율(오탐) ===")
    print(correct["category_flipped"].mean(), f"({correct['category_flipped'].sum()}/{len(correct)})")

    print()
    print(f"=== 옥타브오차 31곡 카테고리 변화 ===")
    print(mismatch["category_flipped"].mean(), f"({mismatch['category_flipped'].sum()}/{len(mismatch)})")
    print(mismatch[["idx", "official_bpm", "m1-bpm_madmom", "official_category",
                     "m1-tempo_category", "category_flipped"]].to_string(index=False))

    check.to_csv(_OUT_FLIP_CSV, index=False, encoding="utf-8-sig")
    print(f"\n저장: {_OUT_FLIP_CSV}")


if __name__ == "__main__":
    main()
