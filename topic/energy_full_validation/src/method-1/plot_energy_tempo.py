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

path = _BRANCH_ROOT / "data" / "songs_master.csv"
rows = []
with open(path, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["eligible_band"].strip().lower() != "true":
            continue
        if not row["energy"].strip() or not row["tempo_excerpt"].strip():
            continue
        rows.append((float(row["energy"]), float(row["tempo_excerpt"])))

energies = np.array([e for e, _ in rows])
tempos = np.array([t for _, t in rows])
r = np.corrcoef(energies, tempos)[0, 1]

fig, ax = plt.subplots(figsize=(6.5, 5.5), dpi=150)
ax.scatter(tempos, energies, s=14, alpha=0.35, color="#256abf", edgecolors="none")
# 추세선(참고용, 상관 거의 없음을 시각적으로도 보여줌)
z = np.polyfit(tempos, energies, 1)
xs = np.linspace(tempos.min(), tempos.max(), 100)
ax.plot(xs, np.polyval(z, xs), color="#e34948", linewidth=2, label=f"선형 추세선 (r={r:.3f})")
ax.set_xlabel("tempo (BPM)", fontsize=10)
ax.set_ylabel("energy (강도, 0~1)", fontsize=10)
ax.set_title(f"energy vs tempo (n={len(rows)}) — 상관관계 거의 없음", fontsize=12, fontweight="bold")
ax.legend(fontsize=9, loc="upper right")
ax.grid(True, alpha=0.25)
fig.tight_layout()
out = _FIG_DIR / "energy_vs_tempo.png"
fig.savefig(out, facecolor="white")
print("saved", out, "r =", r)
