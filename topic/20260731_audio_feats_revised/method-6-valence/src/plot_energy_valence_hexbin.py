"""method-5(arousal) x method-6(valence) 산점도를 밴드별 hexbin으로 시각화.

energy_valence_hexbin.png(전체)와 같은 축 범위/사분면 기준(중간값 5)을 공유하되,
전체 + 밴드별(표본 10곡 이상)을 가로 그리드(한 줄 최대 5개)에 담는다.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_METHOD6_DIR = Path(__file__).resolve().parent.parent
_TOPIC_DIR = _METHOD6_DIR.parent
_ENERGY_CSV = _TOPIC_DIR / "method-5-energy" / "out" / "csv" / "energy_raw.csv"
_VALENCE_CSV = _METHOD6_DIR / "out" / "csv" / "valence_raw.csv"
_OUT_PNG = _METHOD6_DIR / "out" / "fig" / "energy_valence_hexbin.png"

MID = 5.0
MIN_N = 10
GRIDSIZE = 18
NCOLS = 5


def main() -> None:
    energy = pd.read_csv(_ENERGY_CSV)[["idx", "band", "arousal_median"]]
    valence = pd.read_csv(_VALENCE_CSV)[["idx", "valence_median"]]
    df = energy.merge(valence, on="idx")

    band_counts = df["band"].value_counts()
    bands = [b for b in band_counts.index if band_counts[b] >= MIN_N]
    bands = sorted(bands, key=lambda b: -band_counts[b])
    panels = [("전체", df)] + [(b, df[df["band"] == b]) for b in bands]

    xmin, xmax = df["valence_median"].min(), df["valence_median"].max()
    ymin, ymax = df["arousal_median"].min(), df["arousal_median"].max()
    pad_x, pad_y = (xmax - xmin) * 0.03, (ymax - ymin) * 0.03
    xlim = (xmin - pad_x, xmax + pad_x)
    ylim = (ymin - pad_y, ymax + pad_y)

    # 밴드 패널끼리 공유할 색상 스케일(카운트 최대값) — 전체는 표본이 훨씬 커서 별도 스케일
    band_vmaxes = []
    for _, sub in panels[1:]:
        hb = plt.hexbin(sub["valence_median"], sub["arousal_median"],
                         gridsize=GRIDSIZE, extent=(*xlim, *ylim))
        band_vmaxes.append(hb.get_array().max())
        plt.close()
    vmax_band = max(band_vmaxes) if band_vmaxes else None

    nrows = math.ceil(len(panels) / NCOLS)
    fig, axes = plt.subplots(nrows, NCOLS, figsize=(4.0 * NCOLS, 4.4 * nrows))
    axes = np.atleast_2d(axes)

    for i, (label, sub) in enumerate(panels):
        r, c = divmod(i, NCOLS)
        ax = axes[r][c]
        vmax = None if label == "전체" else vmax_band
        hb = ax.hexbin(sub["valence_median"], sub["arousal_median"],
                        gridsize=GRIDSIZE, cmap="inferno", mincnt=1,
                        extent=(*xlim, *ylim), vmax=vmax)
        ax.axvline(MID, color="dimgray", linestyle="--", linewidth=0.8, alpha=0.8)
        ax.axhline(MID, color="dimgray", linestyle="--", linewidth=0.8, alpha=0.8)
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.set_title(f"{label} (n={len(sub)})", fontsize=10)
        ax.set_xlabel("Valence", fontsize=8)
        ax.set_ylabel("Arousal", fontsize=8)
        fig.colorbar(hb, ax=ax, fraction=0.046, pad=0.08)

        if label == "전체":
            quad_kwargs = dict(
                fontsize=7, color="black", fontweight="bold",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.75, pad=1.5),
            )
            ax.text(0.97, 0.97, "고각성+긍정", transform=ax.transAxes,
                    ha="right", va="top", **quad_kwargs)
            ax.text(0.03, 0.97, "고각성+부정", transform=ax.transAxes,
                    ha="left", va="top", **quad_kwargs)
            ax.text(0.97, 0.03, "저각성+긍정", transform=ax.transAxes,
                    ha="right", va="bottom", **quad_kwargs)
            ax.text(0.03, 0.03, "저각성+부정", transform=ax.transAxes,
                    ha="left", va="bottom", **quad_kwargs)

    for i in range(len(panels), nrows * NCOLS):
        r, c = divmod(i, NCOLS)
        axes[r][c].axis("off")

    fig.suptitle(
        "밴드별 Energy(Arousal) x Valence 분포 — 점선: 척도 중간값(5) 기준 사분면 경계",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")


if __name__ == "__main__":
    main()
