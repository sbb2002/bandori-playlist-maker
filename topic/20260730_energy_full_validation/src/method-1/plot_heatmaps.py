"""matplotlib으로 brightness x energy 2D 히트맵(전체 + 밴드별) 정적 PNG 생성.
domain/selection.py의 _brightness_scores() 공식을 그대로 재현한 데이터(songs_master.csv 기반)."""

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Malgun Gothic"  # 한글 렌더링(Windows 기본 한글 폰트)
plt.rcParams["axes.unicode_minus"] = False

_THIS_DIR = Path(__file__).resolve().parent
_TOPIC_DIR = _THIS_DIR.parent.parent
_BRANCH_ROOT = _TOPIC_DIR.parents[1]
_FIG_DIR = _TOPIC_DIR / "fig"

_SHAPE_BRIGHTNESS = {"bright": 0.15, "shimmer": 0.10, "neutral": 0.0, "acoustic": -0.10}

path = _BRANCH_ROOT / "data" / "songs_master.csv"

rows = []
with open(path, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["eligible_band"].strip().lower() != "true":
            continue
        if not row["energy"].strip():
            continue
        rows.append({
            "band": row["band"],
            "mode_score": float(row["mode_score"]),
            "shape": row["shape"],
            "energy": float(row["energy"]),
        })

mode_scores = [r["mode_score"] for r in rows]
lo, hi = min(mode_scores), max(mode_scores)
span = hi - lo
for r in rows:
    norm = (r["mode_score"] - lo) / span if span > 0 else 0.5
    base = norm * 2.0 - 1.0
    adjusted = base + _SHAPE_BRIGHTNESS.get(r["shape"], 0.0)
    r["brightness"] = max(-1.0, min(1.0, adjusted))

E_BINS, B_BINS = 8, 8
e_edges = np.linspace(0, 1, E_BINS + 1)
b_edges = np.linspace(-1, 1, B_BINS + 1)

def build_grid(items):
    energies = [r["energy"] for r in items]
    brightness = [r["brightness"] for r in items]
    grid, _, _ = np.histogram2d(energies, brightness, bins=[e_edges, b_edges])
    return grid  # grid[energy_row, brightness_col]

CMAP = "inferno"  # 검정(적음)→보라/빨강/노랑(많음), viridis보다 극적인 대비

def draw_heatmap(ax, grid, title, annotate_pct=False, n=None, vmax=None):
    data = grid / n * 100 if annotate_pct else grid
    im = ax.imshow(data, origin="lower", cmap=CMAP, aspect="auto",
                    extent=[-1, 1, 0, 1], vmin=0, vmax=vmax)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xlabel("brightness", fontsize=9)
    ax.set_ylabel("energy", fontsize=9)
    ax.set_xticks([-1, -0.5, 0, 0.5, 1])
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
    ax.tick_params(labelsize=8)
    # 셀마다 값 라벨(배경 밝기에 따라 흰/검 자동)
    vmax_eff = vmax if vmax else (data.max() if data.max() > 0 else 1)
    for i in range(E_BINS):
        for j in range(B_BINS):
            v = grid[i, j]
            if v == 0:
                continue
            cx = -1 + (j + 0.5) * (2 / B_BINS)
            cy = (i + 0.5) * (1 / E_BINS)
            frac = data[i, j] / vmax_eff
            color = "black" if frac > 0.55 else "white"  # inferno: 고빈도=밝은 노랑→검정 글씨
            label = f"{int(v)}" if not annotate_pct else f"{int(v)}"
            ax.text(cx, cy, label, ha="center", va="center", fontsize=7.5, color=color)
    return im


# ── 1) 전체 히트맵 ──
fig, ax = plt.subplots(figsize=(6, 6), dpi=150)
overall_grid = build_grid(rows)
im = draw_heatmap(ax, overall_grid, f"전체 (n={len(rows)})")
cbar = fig.colorbar(im, ax=ax, shrink=0.85)
cbar.ax.set_title("곡 수", fontsize=9, pad=8)
fig.tight_layout()
out1 = _FIG_DIR / "heatmap_overall.png"
fig.savefig(out1, facecolor="white")
plt.close(fig)
print("saved", out1)

# ── 2) 밴드별 소형 멀티플 ──
by_band = {}
for r in rows:
    by_band.setdefault(r["band"], []).append(r)

band_order = ["poppin_party","afterglow","pastel_palettes","roselia","hello_happy_world",
              "morfonica","raise_a_suilen","mygo","ave_mujica","mugendai_mutype",
              "various_artists","millsage","ikka_dumb_rock"]
band_order = [b for b in band_order if b in by_band]

ncols = 4
nrows = -(-len(band_order) // ncols)
fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 3.6, nrows * 3.6), dpi=150)
axes_flat = axes.flatten()

# 공통 컬러스케일(비율 기준, 20% 클리핑)
PCT_MAX = 20.0
last_im = None
for idx, band in enumerate(band_order):
    ax = axes_flat[idx]
    items = by_band[band]
    grid = build_grid(items)
    label = band.replace("_", " ").title()
    last_im = draw_heatmap(ax, grid, f"{label} (n={len(items)})", annotate_pct=True, n=len(items), vmax=PCT_MAX)
for idx in range(len(band_order), len(axes_flat)):
    axes_flat[idx].axis("off")

fig.subplots_adjust(hspace=0.55, wspace=0.35, top=0.94, right=0.9)
fig.suptitle("밴드별 brightness x energy 분포 (색상 = 밴드 내 비율%, 공통 스케일 0~20%)", fontsize=13, y=0.99)
cbar = fig.colorbar(last_im, ax=axes_flat.tolist(), shrink=0.6, pad=0.02)
cbar.ax.set_title("%", fontsize=10, pad=8)
out2 = _FIG_DIR / "heatmap_by_band.png"
fig.savefig(out2, facecolor="white")
plt.close(fig)
print("saved", out2)
