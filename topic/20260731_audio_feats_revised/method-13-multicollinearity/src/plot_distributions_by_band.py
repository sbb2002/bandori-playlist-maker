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

MIN_BAND_N = 10  # REPORT.md 관례: 표본 10곡 이상만


def main() -> None:
    df = pd.read_csv(ALL_FEATURES_CSV)
    df["m3-mode_bin"] = (df["m3-mode"] == "major").astype(float)

    band_counts = df["band"].value_counts()
    valid_bands = band_counts[band_counts >= MIN_BAND_N].index.tolist()
    # bpm 대신 표본 크기 큰 순으로 정렬(참고용)
    valid_bands = sorted(valid_bands, key=lambda b: -band_counts[b])
    sub = df[df["band"].isin(valid_bands)].copy()
    print(f"밴드 {len(valid_bands)}개(표본 {MIN_BAND_N}곡 이상), 총 {len(sub)}곡")

    fig, axes = plt.subplots(3, 3, figsize=(18, 14))
    axes = axes.flatten()

    for ax, col in zip(axes, CONTINUOUS_COLS):
        data_by_band = [sub.loc[sub["band"] == b, col].dropna() for b in valid_bands]
        ax.boxplot(data_by_band, tick_labels=valid_bands, showmeans=True,
                    meanprops={"marker": "D", "markerfacecolor": "#C44E52",
                               "markeredgecolor": "#C44E52", "markersize": 4})
        ax.set_title(col, fontsize=10)
        ax.tick_params(axis="x", rotation=60, labelsize=7)
        ax.tick_params(axis="y", labelsize=8)

    # mode: 밴드별 major 비율 막대그래프
    ax = axes[8]
    mode_ratio = sub.groupby("band")["m3-mode_bin"].mean().reindex(valid_bands)
    n_by_band = sub.groupby("band").size().reindex(valid_bands)
    bars = ax.bar(valid_bands, mode_ratio.values, color="#4C72B0")
    for i, (v, n) in enumerate(zip(mode_ratio.values, n_by_band.values)):
        ax.text(i, v, f"{v*100:.0f}%\n(n={n})", ha="center", va="bottom", fontsize=6.5)
    ax.axhline(sub["m3-mode_bin"].mean(), color="#C44E52", linestyle="--", linewidth=1,
                label=f"전체 평균={sub['m3-mode_bin'].mean()*100:.1f}%")
    ax.set_ylim(0, 1.15)
    ax.set_title("m3-mode (major 비율)", fontsize=10)
    ax.tick_params(axis="x", rotation=60, labelsize=7)
    ax.legend(fontsize=7, loc="upper right")

    fig.suptitle(f"사용가능 지표 9종 밴드별 분포 (표본 {MIN_BAND_N}곡 이상 {len(valid_bands)}개 밴드, {len(sub)}곡)",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out_path = OUT_FIG_DIR / "feature_distributions_by_band.png"
    fig.savefig(out_path, dpi=150)
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
