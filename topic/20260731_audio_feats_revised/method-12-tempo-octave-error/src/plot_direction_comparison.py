"""정답군 vs 느리게 오판(half, 0.5x) vs 빠르게 오판(double, 2x) — arousal/valence/acousticness 3종 비교.

'느리게 오판'=원곡이 빠른데 madmom이 절반(0.5x)으로 잡은 경우, '빠르게 오판'=원곡이 느린데
madmom이 두 배(2x)로 잡은 경우. 기타 비정수배 오차(4곡)는 표본 부족으로 제외.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_METHOD12_DIR = Path(__file__).resolve().parent.parent
_TOPIC_DIR = _METHOD12_DIR.parent
_ALL_FEATURES_CSV = _TOPIC_DIR / "data" / "all_features.csv"
_BESTDORI_CSV = _TOPIC_DIR / "method-1-tempo" / "out" / "csv" / "tempo_bestdori_comparison.csv"
_OUT_PNG = _METHOD12_DIR / "out" / "fig" / "direction_comparison_boxplots.png"
_OUT_CSV = _METHOD12_DIR / "out" / "csv" / "direction_comparison_stats.csv"

ORDER = ["correct", "느리게_오판(half)", "빠르게_오판(double)"]
LABEL_MAP = {"correct": "correct", "half(0.5x)": "느리게_오판(half)", "double(2x)": "빠르게_오판(double)"}
COLORS = {"correct": "steelblue", "느리게_오판(half)": "goldenrod", "빠르게_오판(double)": "indianred"}
FEATURES = [
    ("m5-arousal_median", "energy: 각성도"),
    ("m6-valence_median", "valence: 정서적 밝기"),
    ("m8-acoustic_median", "acousticness: 어쿠스틱 확률"),
    ("m4-st_p10", "loudness: short-term p10"),
    ("m4-st_p90", "loudness: short-term p90"),
    ("m4-st_std", "loudness: short-term std"),
]


def main() -> None:
    feats = pd.read_csv(_ALL_FEATURES_CSV)
    bestdori = pd.read_csv(_BESTDORI_CSV)[["idx", "official_bpm", "ratio", "octave_class"]]
    df = bestdori.merge(feats, on="idx", how="left")
    df["group"] = np.where(df["ratio"].between(0.92, 1.08), "correct", df["octave_class"])
    df = df[df["group"].isin(LABEL_MAP)].copy()
    df["group"] = df["group"].map(LABEL_MAP)

    rows = []
    ncols = 3
    nrows = int(np.ceil(len(FEATURES) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(14, 5 * nrows))
    axes = np.atleast_2d(axes).flatten()
    for ax, (col, label) in zip(axes, FEATURES):
        samples = [df.loc[df["group"] == g, col].dropna().values for g in ORDER]
        h, p = stats.kruskal(*samples)
        _, p_ch = stats.mannwhitneyu(samples[0], samples[1])
        _, p_cd = stats.mannwhitneyu(samples[0], samples[2])
        _, p_hd = stats.mannwhitneyu(samples[1], samples[2])

        bp = ax.boxplot(samples, tick_labels=ORDER, patch_artist=True)
        for box, g in zip(bp["boxes"], ORDER):
            box.set_facecolor(COLORS[g])
        ax.tick_params(axis="x", rotation=15)
        sig = " *" if p < 0.05 else ""
        ax.set_title(
            f"{label}\n({col})\nKruskal p={p:.4f}{sig}\n"
            f"correct-half p={p_ch:.3f} | correct-double p={p_cd:.3f} | half-double p={p_hd:.3f}",
            fontsize=9,
        )

        for g, s in zip(ORDER, samples):
            rows.append({
                "feature": col, "group": g, "n": len(s),
                "median": np.median(s), "mean": np.mean(s), "std": np.std(s),
                "kruskal_p": p, "vs_correct_p": (np.nan if g == "correct" else (p_ch if g == "느리게_오판(half)" else p_cd)),
            })

    for ax in axes[len(FEATURES):]:
        ax.axis("off")

    fig.suptitle(
        "correct vs 느리게_오판(half, 0.5x) vs 빠르게_오판(double, 2x) — "
        "arousal/valence/acousticness + loudness(p10/p90/std)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")

    result = pd.DataFrame(rows)
    result.to_csv(_OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"저장: {_OUT_CSV}")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
