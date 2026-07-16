"""Step 4b — plot existing indicators + research-target indicators for the
39 selected tracks, grouped by band.

Existing indicators (song_features_with_proxies.csv):
  mode_score, energy_proxy, acousticness_proxy, instrumentalness_proxy,
  harmonic_ratio, voiced_frac_mix
Research-target indicators (mood_warmth vocal-phonation study):
  f0_range_st, hnr_mean, shimmer_local, jitter_local, vocal_ratio, vocal_centroid

One PNG per metric: horizontal bars, one per track, grouped/colored by band.
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
# CJK 폰트 설정: 일본어 제목 렌더링 지원
from matplotlib import font_manager
_available = {f.name for f in font_manager.fontManager.ttflist}
for _cand in ("Yu Gothic", "MS Gothic", "Meiryo", "Malgun Gothic"):
    if _cand in _available:
        matplotlib.rcParams["font.family"] = _cand
        break
matplotlib.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt
import matplotlib.cm as cm

HERE = os.path.dirname(os.path.abspath(__file__))
IN_CSV = os.path.join(HERE, "combined_metrics.csv")
OUT_DIR = os.path.join(HERE, "fig", "metrics")

EXISTING_METRICS = ["mode_score", "energy_proxy", "acousticness_proxy",
                     "instrumentalness_proxy", "harmonic_ratio", "voiced_frac_mix"]
RESEARCH_METRICS = ["f0_range_st", "hnr_mean", "shimmer_local", "jitter_local",
                     "vocal_ratio", "vocal_centroid"]


def plot_metric(df, col, out_path):
    d = df.dropna(subset=[col]).copy()
    d = d.sort_values(["band", "idx"])
    bands = sorted(d["band"].unique())
    cmap = cm.get_cmap("tab10", len(bands))
    band_color = {b: cmap(i) for i, b in enumerate(bands)}
    colors = [band_color[b] for b in d["band"]]
    labels = [f"{b}/{s}" for b, s in zip(d["band"], d["song"])]

    fig, ax = plt.subplots(figsize=(9, max(4, 0.28 * len(d))))
    ax.barh(range(len(d)), d[col], color=colors)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel(col)
    ax.set_title(f"{col} — {len(d)} tracks ({d['band'].nunique()} bands x 3 songs)")

    handles = [plt.Rectangle((0, 0), 1, 1, color=band_color[b]) for b in bands]
    ax.legend(handles, bands, fontsize=6, loc="lower right", ncol=2)

    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_csv(IN_CSV)
    for col in EXISTING_METRICS + RESEARCH_METRICS:
        if col not in df.columns:
            print(f"skip missing column {col}")
            continue
        out_path = os.path.join(OUT_DIR, f"{col}.png")
        plot_metric(df, col, out_path)
        print(f"plotted {col} -> {out_path}")


if __name__ == "__main__":
    main()
