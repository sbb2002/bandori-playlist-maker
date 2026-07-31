"""energy_full x brightness 밴드별 소형 멀티플. brightness는 domain/selection.py의
_brightness_scores() 공식(eligible 풀 전체 1회 정규화)을 재현, energy_full은 비율(%) 기준."""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_TOPIC_DIR = Path(__file__).resolve().parent.parent.parent
_BRANCH_ROOT = _TOPIC_DIR.parents[1]
_FIG_DIR = _TOPIC_DIR / "fig"

_SHAPE_BRIGHTNESS = {"bright": 0.15, "shimmer": 0.10, "neutral": 0.0, "acoustic": -0.10}

path = _BRANCH_ROOT / "data" / "songs_master.csv"

all_eligible = []
with open(path, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["eligible_band"].strip().lower() != "true":
            continue
        all_eligible.append(row)

mode_scores = [float(r["mode_score"]) for r in all_eligible]
lo, hi = min(mode_scores), max(mode_scores)
span = hi - lo
for r in all_eligible:
    norm = (float(r["mode_score"]) - lo) / span if span > 0 else 0.5
    base = norm * 2.0 - 1.0
    adjusted = base + _SHAPE_BRIGHTNESS.get(r["shape"], 0.0)
    r["brightness"] = max(-1.0, min(1.0, adjusted))

rows = [r for r in all_eligible if r["energy_full"].strip()]

by_band = defaultdict(list)
for r in rows:
    by_band[r["band"]].append(r)

band_order = ["poppin_party","afterglow","pastel_palettes","roselia","hello_happy_world",
              "morfonica","raise_a_suilen","mygo","ave_mujica","mugendai_mutype",
              "various_artists","millsage","ikka_dumb_rock"]
band_order = [b for b in band_order if b in by_band]

E_BINS, B_BINS = 8, 8
e_edges = np.linspace(0, 1, E_BINS + 1)
b_edges = np.linspace(-1, 1, B_BINS + 1)
PCT_MAX = 20.0

ncols = 4
nrows = -(-len(band_order) // ncols)
fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.6, nrows * 3.6), dpi=150)
axes_flat = axes.flatten()

last_im = None
for idx, band in enumerate(band_order):
    ax = axes_flat[idx]
    items = by_band[band]
    n = len(items)
    ef = np.array([float(r["energy_full"]) for r in items])
    br = np.array([r["brightness"] for r in items])
    grid, _, _ = np.histogram2d(ef, br, bins=[e_edges, b_edges])
    pct = grid / n * 100
    im = ax.imshow(pct, origin="lower", cmap="inferno", aspect="auto", extent=[-1, 1, 0, 1], vmin=0, vmax=PCT_MAX)
    label = band.replace("_", " ").title()
    ax.set_title(f"{label} (n={n})", fontsize=11, fontweight="bold")
    ax.set_xlabel("brightness", fontsize=9)
    ax.set_ylabel("energy_full", fontsize=9)
    ax.set_xticks([-1, -0.5, 0, 0.5, 1])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
    ax.tick_params(labelsize=8)
    for i in range(E_BINS):
        for j in range(B_BINS):
            v = grid[i, j]
            if v == 0:
                continue
            cx = -1 + (j + 0.5) * (2 / B_BINS)
            cy = (i + 0.5) * (1 / E_BINS)
            color = "black" if pct[i, j] / PCT_MAX > 0.55 else "white"  # inferno: 고빈도=밝은 노랑→검정 글씨
            ax.text(cx, cy, f"{int(v)}", ha="center", va="center", fontsize=7.5, color=color)
    last_im = im

for idx in range(len(band_order), len(axes_flat)):
    axes_flat[idx].axis("off")

fig.subplots_adjust(hspace=0.55, wspace=0.35, top=0.94, right=0.9)
fig.suptitle("밴드별 energy_full x brightness 분포 (색상 = 밴드 내 비율%, 공통 스케일 0~20%)", fontsize=13, y=0.99)
cbar = fig.colorbar(last_im, ax=axes_flat.tolist(), shrink=0.6, pad=0.02)
cbar.ax.set_title("%", fontsize=10, pad=8)

out = _FIG_DIR / "heatmap_energyfull_brightness_byband.png"
fig.savefig(out, facecolor="white")
print("saved", out)
