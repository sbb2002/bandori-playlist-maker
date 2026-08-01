"""arousal(method-5) x valence(method-6) x danceability_norm(method-7) x lra(method-4)
4개 지표를 밴드별 레이더 차트로 시각화.

RAS(regular groove 가설)와 roselia(free-form dramatic 가설)처럼, arousal·valence만으로는
구분 안 되던 밴드들이 danceability/lra 축을 더하면 어떻게 갈라지는지 확인하기 위한
교차분석용 플롯. 각 지표는 밴드 중앙값을 밴드 간 min-max로 0~1 정규화해 같은 축 위에서
비교 가능하게 만든다(레이더 차트는 스케일이 다른 지표를 그대로 겹치면 왜곡되므로).
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_METHOD7_DIR = Path(__file__).resolve().parent.parent
_TOPIC_DIR = _METHOD7_DIR.parent
_DANCE_CSV = _METHOD7_DIR / "out" / "csv" / "danceability_raw.csv"
_ENERGY_CSV = _TOPIC_DIR / "method-5-energy" / "out" / "csv" / "energy_raw.csv"
_VALENCE_CSV = _TOPIC_DIR / "method-6-valence" / "out" / "csv" / "valence_raw.csv"
_LOUD_CSV = _TOPIC_DIR / "method-4-loudness" / "out" / "csv" / "loudness_raw.csv"
_OUT_PNG = _METHOD7_DIR / "out" / "fig" / "band_profile_radar.png"

MIN_N = 10
NCOLS = 5
# lra는 "규칙성/그루브"와 반대 방향(값이 클수록 다이내믹 기복↑)이므로 축 라벨에 명시하고
# 방향을 뒤집지 않고 그대로 사용한다(있는 그대로의 물리적 의미를 보존).
AXES = ["arousal_median", "valence_median", "danceability_norm", "lra"]
AXIS_LABELS = ["Arousal\n(각성도)", "Valence\n(밝기)", "Danceability\n(리듬 규칙성)", "LRA\n(다이내믹 기복)"]


def main() -> None:
    dance = pd.read_csv(_DANCE_CSV)[["idx", "band", "danceability_norm"]]
    energy = pd.read_csv(_ENERGY_CSV)[["idx", "arousal_median"]]
    valence = pd.read_csv(_VALENCE_CSV)[["idx", "valence_median"]]
    loud = pd.read_csv(_LOUD_CSV)[["idx", "lra"]]
    df = dance.merge(energy, on="idx").merge(valence, on="idx").merge(loud, on="idx")

    band_counts = df["band"].value_counts()
    bands = [b for b in band_counts.index if band_counts[b] >= MIN_N]
    medians = df[df["band"].isin(bands)].groupby("band")[AXES].median()

    # 밴드 간 min-max 정규화(0~1) — 레이더 축 간 스케일을 맞추기 위함
    norm = (medians - medians.min()) / (medians.max() - medians.min())
    overall_norm = norm.mean()  # 참고선(전 밴드 평균 프로필)

    bands_sorted = norm.sort_values("danceability_norm", ascending=False).index.tolist()

    n_axes = len(AXES)
    angles = [n / float(n_axes) * 2 * math.pi for n in range(n_axes)]
    angles += angles[:1]

    nrows = math.ceil(len(bands_sorted) / NCOLS)
    fig, axes = plt.subplots(nrows, NCOLS, figsize=(3.6 * NCOLS, 4.6 * nrows),
                              subplot_kw=dict(polar=True))
    axes = np.atleast_2d(axes)

    for i, band in enumerate(bands_sorted):
        r, c = divmod(i, NCOLS)
        ax = axes[r][c]

        ref_vals = overall_norm.tolist() + overall_norm.tolist()[:1]
        ax.plot(angles, ref_vals, color="gray", linewidth=1, linestyle="--", alpha=0.6)
        ax.fill(angles, ref_vals, color="gray", alpha=0.05)

        vals = norm.loc[band, AXES].tolist()
        vals += vals[:1]
        ax.plot(angles, vals, color="crimson", linewidth=2)
        ax.fill(angles, vals, color="crimson", alpha=0.2)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(AXIS_LABELS, fontsize=7)
        ax.set_yticks([0.25, 0.5, 0.75])
        ax.set_yticklabels([])
        ax.set_ylim(0, 1)
        n = band_counts[band]
        ax.set_title(f"{band} (n={n})", fontsize=10, pad=14)

    for i in range(len(bands_sorted), nrows * NCOLS):
        r, c = divmod(i, NCOLS)
        axes[r][c].axis("off")

    fig.suptitle(
        "밴드별 4축 프로필 — Arousal x Valence x Danceability x LRA (밴드 중앙값, min-max 정규화)\n"
        "빨강=해당 밴드, 회색 점선=전 밴드 평균 프로필",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.subplots_adjust(hspace=0.6, wspace=0.4)
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")

    print()
    print(norm.loc[bands_sorted].round(3))


if __name__ == "__main__":
    main()
