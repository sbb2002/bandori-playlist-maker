from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_TOPIC_DIR = _METHOD_DIR.parent

ALL_FEATURES_CSV = _TOPIC_DIR / "data" / "all_features.csv"
OUT_FIG_DIR = _METHOD_DIR / "out" / "fig"

CONTINUOUS_COLS = [
    "m4-lufs_integrated",
    "m4-lra",
    "m5-arousal_median",
    "m6-valence_median",
    "m7-danceability_norm",
    "m8-acoustic_median",
    "m9-instr_stem_ratio",
    "m11-speech_median",
]


def main() -> None:
    df = pd.read_csv(ALL_FEATURES_CSV)
    df["m3-mode_bin"] = (df["m3-mode"] == "major").astype(float)

    fig, axes = plt.subplots(3, 3, figsize=(13, 11))
    axes = axes.flatten()

    for ax, col in zip(axes, CONTINUOUS_COLS):
        data = df[col].dropna()
        ax.hist(data, bins=40, color="#4C72B0", edgecolor="white", linewidth=0.3)
        ax.axvline(data.median(), color="#C44E52", linestyle="--", linewidth=1,
                    label=f"median={data.median():.3g}")
        ax.set_title(col, fontsize=10)
        ax.legend(fontsize=7, loc="upper right")

    # mode: 범주형이므로 막대그래프
    ax = axes[8]
    counts = df["m3-mode"].value_counts()
    ax.bar(counts.index.astype(str), counts.values, color=["#4C72B0", "#DD8452"])
    for i, v in enumerate(counts.values):
        ax.text(i, v, f"{v}\n({v/counts.sum()*100:.1f}%)", ha="center", va="bottom", fontsize=8)
    ax.set_title("m3-mode", fontsize=10)

    fig.suptitle("사용가능 지표 9종 분포 (736곡)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out_path = OUT_FIG_DIR / "feature_distributions.png"
    fig.savefig(out_path, dpi=150)
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
