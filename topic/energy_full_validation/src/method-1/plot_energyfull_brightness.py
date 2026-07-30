"""energy_full x brightness 2D 히트맵. brightness는 domain/selection.py의
_brightness_scores() 공식(mode_score min-max 정규화 + shape 보조가중, eligible_band 풀
전체 1회 정규화)을 그대로 재현."""

import csv
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

# brightness 정규화는 production과 동일하게 eligible 풀 "전체" 기준(energy_full 결측 포함)으로 계산.
mode_scores = [float(r["mode_score"]) for r in all_eligible]
lo, hi = min(mode_scores), max(mode_scores)
span = hi - lo
for r in all_eligible:
    norm = (float(r["mode_score"]) - lo) / span if span > 0 else 0.5
    base = norm * 2.0 - 1.0
    adjusted = base + _SHAPE_BRIGHTNESS.get(r["shape"], 0.0)
    r["brightness"] = max(-1.0, min(1.0, adjusted))

rows = [r for r in all_eligible if r["energy_full"].strip()]
print("n =", len(rows))

brightness = np.array([r["brightness"] for r in rows])
energy_full = np.array([float(r["energy_full"]) for r in rows])
r_val = np.corrcoef(brightness, energy_full)[0, 1]
print("Pearson r(brightness, energy_full) =", r_val)

E_BINS, B_BINS = 8, 8
e_edges = np.linspace(0, 1, E_BINS + 1)
b_edges = np.linspace(-1, 1, B_BINS + 1)
grid, _, _ = np.histogram2d(energy_full, brightness, bins=[e_edges, b_edges])

fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=150)
im = ax.imshow(grid, origin="lower", cmap="inferno", aspect="auto", extent=[-1, 1, 0, 1])
ax.set_title(f"energy_full x brightness (n={len(rows)}, r={r_val:.3f})", fontsize=12, fontweight="bold")
ax.set_xlabel("brightness", fontsize=10)
ax.set_ylabel("energy_full", fontsize=10)
ax.set_xticks([-1, -0.5, 0, 0.5, 1])
ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
vmax = grid.max()
for i in range(E_BINS):
    for j in range(B_BINS):
        v = grid[i, j]
        if v == 0:
            continue
        cx = -1 + (j + 0.5) * (2 / B_BINS)
        cy = (i + 0.5) * (1 / E_BINS)
        color = "black" if v / vmax > 0.55 else "white"  # inferno: 고빈도=밝은 노랑→검정 글씨
        ax.text(cx, cy, f"{int(v)}", ha="center", va="center", fontsize=8.5, color=color)
cbar = fig.colorbar(im, ax=ax, shrink=0.85)
cbar.ax.set_title("곡 수", fontsize=9, pad=8)
fig.tight_layout()

out = _FIG_DIR / "heatmap_energyfull_brightness.png"
fig.savefig(out, facecolor="white")
print("saved", out)
