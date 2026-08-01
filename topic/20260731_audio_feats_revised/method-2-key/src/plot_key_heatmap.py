"""key_raw.csv(key_ks, mode_ks)를 12key x 2mode 히트맵으로 시각화.

산출물: ../out/key_heatmap.png — 전체 + 밴드별(표본 10곡 미만 제외) 히트맵을
가로 방향 그리드(한 줄 최대 5개)로 한 파일에 모두 담는다. 색상은 inferno.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_IN_CSV = _METHOD_DIR / "out" / "csv" / "key_raw.csv"
_OUT_PNG = _METHOD_DIR / "out" / "fig" / "key_heatmap.png"

KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MODES = ["major", "minor"]
MIN_N = 10
CMAP = "inferno"


def key_mode_matrix(df: pd.DataFrame) -> np.ndarray:
    mat = np.zeros((len(KEYS), len(MODES)), dtype=int)
    for i, k in enumerate(KEYS):
        for j, m in enumerate(MODES):
            mat[i, j] = ((df["key_ks"] == k) & (df["mode_ks"] == m)).sum()
    return mat


def draw_heatmap(ax, mat: np.ndarray, title: str, vmax: float) -> None:
    im = ax.imshow(mat, cmap=CMAP, aspect="auto", vmin=0, vmax=vmax)
    totals = mat.sum(axis=0)  # [major 합계, minor 합계]
    ax.set_xticks(range(len(MODES)))
    ax.set_xticklabels([f"{m}\n(n={t})" for m, t in zip(MODES, totals)], fontsize=9)
    ax.set_yticks(range(len(KEYS)))
    ax.set_yticklabels(KEYS, fontsize=9)
    ax.set_title(title, fontsize=10)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            # inferno: 값이 클수록 밝은 노랑 배경 -> 검은 글씨, 작을수록 어두운 보라 -> 흰 글씨
            color = "black" if v > vmax * 0.5 else "white"
            ax.text(j, i, str(v), ha="center", va="center", fontsize=8, color=color)
    return im


def main() -> None:
    df = pd.read_csv(_IN_CSV)
    df = df[(df["error"].isna()) | (df["error"] == "")]
    df = df[df["key_ks"].notna() & df["mode_ks"].notna()].copy()

    band_counts = df["band"].value_counts()
    bands = [b for b in band_counts.index if band_counts[b] >= MIN_N]
    bands = sorted(bands, key=lambda b: -band_counts[b])

    panels = [("전체", df)] + [(b, df[df["band"] == b]) for b in bands]
    mats = [key_mode_matrix(sub) for _, sub in panels]
    # "전체"는 자체 스케일(압도적으로 n이 커서 같이 묶으면 밴드별 패널이 다 눌림), 나머지
    # 밴드들은 서로 비교 가능하도록 하나의 공유 스케일(0~vmax_band)을 쓴다.
    vmax_all = mats[0].max()
    vmax_band = max(m.max() for m in mats[1:])
    vmaxes = [vmax_all] + [vmax_band] * (len(mats) - 1)

    # 가로 방향 그리드: 한 줄 최대 5개
    ncols = 5
    nrows = math.ceil(len(panels) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.2 * ncols, 4.6 * nrows))
    axes = np.atleast_2d(axes)
    for i, ((label, sub), mat, vmax) in enumerate(zip(panels, mats, vmaxes)):
        r, c = divmod(i, ncols)
        im = draw_heatmap(axes[r][c], mat, f"{label} (n={len(sub)})", vmax)
        fig.colorbar(im, ax=axes[r][c], fraction=0.046, pad=0.08)
    for i in range(len(panels), nrows * ncols):
        r, c = divmod(i, ncols)
        axes[r][c].axis("off")

    fig.suptitle("Key(K-S) 분포 — 12key x 2mode", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")


if __name__ == "__main__":
    main()
