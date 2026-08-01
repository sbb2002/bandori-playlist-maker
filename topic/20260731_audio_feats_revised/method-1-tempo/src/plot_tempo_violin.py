"""tempo_raw.csv의 bpm_madmom 분포를 전체 및 밴드별 바이올린 플롯으로 저장.

산출물: ../out/tempo_violin.png
표본 10곡 미만 밴드(various_artists/ikka_dumb_rock/millsage)는 바이올린 형태가
무의미해 제외한다. 밴드는 중앙값 내림차순 정렬, 맨 왼쪽에 전체(집계) 배치.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"  # Windows 한글 폰트 (레이블 깨짐 방지)
plt.rcParams["axes.unicode_minus"] = False

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_IN_CSV = _METHOD_DIR / "out" / "csv" / "tempo_raw.csv"
_OUT_PNG = _METHOD_DIR / "out" / "fig" / "tempo_violin.png"

MIN_N = 10

COLOR_ALL = "#4a3aa7"
COLOR_BAND = "#2a78d6"


def load_bpm_by_band() -> dict[str, list[float]]:
    data: dict[str, list[float]] = {}
    with _IN_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("error"):
                continue
            v = (r.get("bpm_madmom") or "").strip()
            if not v:
                continue
            data.setdefault(r["band"], []).append(float(v))
    return {k: v for k, v in data.items() if len(v) >= MIN_N}


def style_violin(parts, color: str) -> None:
    for body in parts["bodies"]:
        body.set_facecolor(color)
        body.set_edgecolor(color)
        body.set_alpha(0.28)
        body.set_linewidth(1.25)
    for key in ("cmedians", "cbars", "cmins", "cmaxes"):
        if key in parts:
            parts[key].set_edgecolor(color)
            parts[key].set_linewidth(1.5 if key == "cmedians" else 1.0)


def main() -> None:
    by_band = load_bpm_by_band()
    band_order = sorted(by_band, key=lambda k: -float(np.median(by_band[k])))
    all_values = [v for vs in by_band.values() for v in vs]

    groups = [("전체", all_values, True)] + [(b, by_band[b], False) for b in band_order]
    labels = [g[0] for g in groups]
    values = [g[1] for g in groups]

    fig, ax = plt.subplots(figsize=(12, 6))

    for i, (label, vals, is_all) in enumerate(groups, start=1):
        parts = ax.violinplot(
            [vals], positions=[i], widths=0.8, showmedians=True, showextrema=True
        )
        style_violin(parts, COLOR_ALL if is_all else COLOR_BAND)
        n = len(vals)
        ax.text(
            i,
            1.01,
            f"n={n}",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=8,
            color="#666",
        )

    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("bpm_madmom")
    ax.set_title("Tempo(bpm_madmom) 분포 — 전체 & 밴드별 (n<10 밴드 제외)", pad=28)
    ax.grid(axis="y", linestyle="-", linewidth=0.5, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    handles = [
        plt.Line2D([0], [0], color=COLOR_ALL, lw=6, alpha=0.5, label="전체(집계)"),
        plt.Line2D([0], [0], color=COLOR_BAND, lw=6, alpha=0.5, label="개별 밴드"),
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False, fontsize=9)

    fig.tight_layout()
    fig.savefig(_OUT_PNG, dpi=150)
    print(f"저장: {_OUT_PNG}")


if __name__ == "__main__":
    main()
