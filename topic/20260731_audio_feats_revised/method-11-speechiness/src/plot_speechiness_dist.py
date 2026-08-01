"""speechiness_dist.png 재생성 — 밴드별 박스플롯에 중앙값 기준 컬러맵 대비 적용.

기존 버전은 밴드별 박스를 전부 같은 단색(speech_median=하늘색, vad_speech_ratio=
살구색)으로 칠해서, speech_median은 박스 위치로 밴드 차이가 보였지만 vad_speech_ratio는
분산이 크고 박스 색이 균일해 밴드별 차이가 시각적으로 잘 안 들어온다는 지적을 반영해
밴드 중앙값 순위에 따라 컬러맵(RdYlBu_r)을 입힌다.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_METHOD11_DIR = Path(__file__).resolve().parent.parent
_CSV = _METHOD11_DIR / "out" / "csv" / "speechiness_raw.csv"
_OUT_PNG = _METHOD11_DIR / "out" / "fig" / "speechiness_dist.png"

MIN_N = 10
CMAP = plt.get_cmap("RdYlBu_r")


def _colored_boxplot(ax, df, band_order, col, title, ylabel):
    data = [df[df["band"] == b][col].dropna().values for b in band_order]
    medians = [np.median(d) for d in data]
    order_rank = pd.Series(medians).rank(pct=True).values  # 0~1로 정규화된 순위

    bp = ax.boxplot(data, labels=band_order, patch_artist=True, showfliers=True)
    for patch, rank in zip(bp["boxes"], order_rank):
        patch.set_facecolor(CMAP(rank))
        patch.set_alpha(0.85)
    for median_line in bp["medians"]:
        median_line.set_color("black")
        median_line.set_linewidth(1.5)

    ax.set_title(title, fontsize=12)
    ax.set_xlabel("밴드")
    ax.set_ylabel(ylabel)
    ax.tick_params(axis="x", rotation=45)


def main() -> None:
    df = pd.read_csv(_CSV)
    band_counts = df["band"].value_counts()
    bands = [b for b in band_counts.index if band_counts[b] >= MIN_N]
    # speech_median 중앙값 기준 정렬(기존 버전과 동일 순서 유지)
    band_order = (
        df[df["band"].isin(bands)]
        .groupby("band")["speech_median"]
        .median()
        .sort_values()
        .index.tolist()
    )

    fig = plt.figure(figsize=(20, 15.5))
    gs = fig.add_gridspec(2, 3)

    # --- 1행: 분포 히스토그램 x2 + 산점도 ---
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.hist(df["speech_median"].dropna(), bins=40, color="steelblue", edgecolor="black", alpha=0.8)
    s = df["speech_median"]
    ax1.set_title("speech_median 분포", fontsize=12)
    ax1.set_xlabel("speech_median (4Hz 변조 에너지)")
    ax1.set_ylabel("빈도")
    ax1.text(0.97, 0.97, f"Mean: {s.mean():.4f}\nStd: {s.std():.4f}\nMin: {s.min():.4f}\nMax: {s.max():.4f}",
              transform=ax1.transAxes, ha="right", va="top", fontsize=9,
              bbox=dict(facecolor="wheat", alpha=0.6))

    ax2 = fig.add_subplot(gs[0, 1])
    v = df["vad_speech_ratio"]
    ax2.hist(v.dropna(), bins=40, color="coral", edgecolor="black", alpha=0.8)
    ax2.set_title("vad_speech_ratio 분포", fontsize=12)
    ax2.set_xlabel("vad_speech_ratio (VAD 기반)")
    ax2.set_ylabel("빈도")
    ax2.text(0.97, 0.97, f"Mean: {v.mean():.4f}\nStd: {v.std():.4f}\nMin: {v.min():.4f}\nMax: {v.max():.4f}",
              transform=ax2.transAxes, ha="right", va="top", fontsize=9,
              bbox=dict(facecolor="wheat", alpha=0.6))

    ax3 = fig.add_subplot(gs[0, 2])
    ax3.scatter(df["speech_median"], df["vad_speech_ratio"], color="seagreen", alpha=0.6, edgecolor="black", linewidths=0.3)
    corr = df["speech_median"].corr(df["vad_speech_ratio"], method="spearman")
    ax3.set_title("두 지표 산점도", fontsize=12)
    ax3.set_xlabel("speech_median")
    ax3.set_ylabel("vad_speech_ratio")
    ax3.text(0.97, 0.03, f"Spearman rho = {corr:.4f}\np-value < 0.001\nn = {len(df)}",
              transform=ax3.transAxes, ha="right", va="bottom", fontsize=9,
              bbox=dict(facecolor="lightyellow", alpha=0.8))

    # --- 2행: 밴드별 박스플롯(컬러맵 대비 적용) x2 + 요약표 ---
    ax4 = fig.add_subplot(gs[1, 0])
    _colored_boxplot(ax4, df, band_order, "speech_median",
                      "밴드별 speech_median 박스플롯\n(표본 10곡 이상, 색=밴드 중앙값 순위)", "speech_median")

    ax5 = fig.add_subplot(gs[1, 1])
    _colored_boxplot(ax5, df, band_order, "vad_speech_ratio",
                      "밴드별 vad_speech_ratio 박스플롯\n(표본 10곡 이상, 색=밴드 중앙값 순위)", "vad_speech_ratio")

    ax6 = fig.add_subplot(gs[1, 2])
    ax6.axis("off")
    summary = (
        df[df["band"].isin(bands)]
        .groupby("band")
        .agg(N=("song", "count"),
             Speech_Mean=("speech_median", "mean"), Speech_Std=("speech_median", "std"),
             VAD_Mean=("vad_speech_ratio", "mean"), VAD_Std=("vad_speech_ratio", "std"))
        .loc[[b for b in band_order[::-1]]]
        .round(4)
    )
    table_text = summary.to_string()
    ax6.text(0.02, 0.98, f"밴드별 요약통계 (표본 10곡 이상)\n\n{table_text}",
              transform=ax6.transAxes, ha="left", va="top", fontsize=8.5,
              bbox=dict(facecolor="lightyellow", alpha=0.8))

    fig.tight_layout()
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")


if __name__ == "__main__":
    main()
