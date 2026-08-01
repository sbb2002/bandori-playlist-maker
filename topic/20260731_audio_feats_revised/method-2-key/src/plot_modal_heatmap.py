"""modal_key_validation_full.csv(736곡, 12key x 7교회선법)를 히트맵으로 시각화.

key_heatmap.png(12key x 2mode)와 같은 레이아웃 — 전체 + 밴드별(표본 10곡 이상)을
가로 그리드(한 줄 최대 5개)에 담되, 열은 major/minor 2개가 아니라 7개 교회선법으로
확장한다. 열 라벨은 major/minor 약칭 없이 ionian/dorian/phrygian/lydian/mixolydian/
aeolian/locrian 모드명으로 통일한다(ionian=장조, aeolian=단조).

⚠️ 이 모드 분류는 실증 검증된 K-S major/minor와 달리, major/minor 프로파일에서
특징음 가중치를 맞바꾼 휴리스틱 근사 템플릿 기반이다(method-2-key/src/
extract_key_modal.py 참고) — 참고용으로만 해석할 것.
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
_IN_CSV = _METHOD_DIR / "out" / "csv" / "modal_key_validation_full.csv"
_OUT_PNG = _METHOD_DIR / "out" / "fig" / "modal_key_heatmap.png"

KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# 모드 순서(교회선법 순). 열 라벨은 major/minor 약칭 없이 모드명으로 통일한다.
MODES = [
    ("ionian", ""),
    ("dorian", ""),
    ("phrygian", ""),
    ("lydian", ""),
    ("mixolydian", ""),
    ("aeolian", ""),
    ("locrian", ""),
]
MODE_NAMES = [m for m, _ in MODES]
COL_LABELS = MODE_NAMES
MIN_N = 10
CMAP = "inferno"


def key_mode_matrix(df: pd.DataFrame) -> np.ndarray:
    mat = np.zeros((len(KEYS), len(MODES)), dtype=int)
    for i, k in enumerate(KEYS):
        for j, (mode, _) in enumerate(MODES):
            mat[i, j] = ((df["key_modal"] == k) & (df["mode_modal"] == mode)).sum()
    return mat


def draw_heatmap(ax, mat: np.ndarray, title: str, vmax: float) -> None:
    im = ax.imshow(mat, cmap=CMAP, aspect="auto", vmin=0, vmax=vmax)
    ax.set_xticks(range(len(MODES)))
    ax.set_xticklabels(COL_LABELS, fontsize=7, rotation=45, ha="right")
    ax.set_yticks(range(len(KEYS)))
    ax.set_yticklabels(KEYS, fontsize=8)
    ax.set_title(title, fontsize=10)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat[i, j]
            if v == 0:
                continue
            color = "black" if v > vmax * 0.5 else "white"
            ax.text(j, i, str(v), ha="center", va="center", fontsize=7, color=color)
    return im


def main() -> None:
    df = pd.read_csv(_IN_CSV)

    band_counts = df["band"].value_counts()
    bands = [b for b in band_counts.index if band_counts[b] >= MIN_N]
    bands = sorted(bands, key=lambda b: -band_counts[b])

    panels = [("전체", df)] + [(b, df[df["band"] == b]) for b in bands]
    mats = [key_mode_matrix(sub) for _, sub in panels]
    vmax_all = mats[0].max()
    vmax_band = max(m.max() for m in mats[1:])
    vmaxes = [vmax_all] + [vmax_band] * (len(mats) - 1)

    ncols = 5
    nrows = math.ceil(len(panels) / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.6 * ncols, 4.8 * nrows))
    axes = np.atleast_2d(axes)
    for i, ((label, sub), mat, vmax) in enumerate(zip(panels, mats, vmaxes)):
        r, c = divmod(i, ncols)
        im = draw_heatmap(axes[r][c], mat, f"{label} (n={len(sub)})", vmax)
        fig.colorbar(im, ax=axes[r][c], fraction=0.046, pad=0.08)
    for i in range(len(panels), nrows * ncols):
        r, c = divmod(i, ncols)
        axes[r][c].axis("off")

    fig.suptitle(
        "모드 스케일 확장 key 분포 — 12key x 7교회선법 "
        "(ionian=장조, aeolian=단조, 나머지 5개는 그 외 교회선법) "
        "— [주의] 휴리스틱 근사, 참고용",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")


if __name__ == "__main__":
    main()
