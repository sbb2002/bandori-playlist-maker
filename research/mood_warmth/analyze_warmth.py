"""Step 3 — Statistical analysis of vocal warmth/pathos features (n=29).

Deterministic. Produces analysis_results.md (utf-8 tables) and fig/*.png scatter
plots for the top-3 Spearman features. Anchors (idx 208/196/78) are excluded from
the n=29 statistics and reported separately.
"""
import io
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSHEET = os.path.join(HERE, "candidates_worksheet.csv")
VOCAL_CSV = os.path.join(HERE, "vocal_features.csv")
CORPUS_CSV = r"C:\Users\User\Documents\pyworks\bandori-song-sorter\docs\working\report\genre-features\song_features_with_proxies.csv"
OUT_MD = os.path.join(HERE, "analysis_results.md")
FIG_DIR = os.path.join(HERE, "fig")

BASELINE = ["dist", "mode_score", "harmonic_ratio", "contrast", "rms", "voiced_frac_mix"]
CONTROLS = ["mode_score", "voiced_frac_mix"]
NEW_FEATURES = ["jitter_local", "shimmer_local", "hnr_mean", "f0_median_st",
                "f0_range_st", "f0_std_st", "vocal_ratio", "vocal_centroid",
                "incongruence"]
ANCHOR_IDX = [(("morfonica", 208), "esora no clover"),
              (("morfonica", 196), "Sonorous"),
              (("ave_mujica", 78), "天球のMúsica")]


def zscore_cols(df, cols):
    z = df[cols].copy()
    for c in cols:
        z[c] = (df[c] - df[c].mean()) / df[c].std(ddof=1)
    return z.values


def ols_r2(y, Xcols):
    X = np.column_stack([np.ones(len(y)), Xcols])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1.0 - ss_res / ss_tot


def residualize(y, controls):
    X = np.column_stack([np.ones(len(y)), controls])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def bh_fdr(pvals):
    p = np.asarray(pvals, float)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * m / (np.arange(1, m + 1))
    # enforce monotonicity (from largest to smallest)
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    out = np.empty(m)
    out[order] = q
    return out


def main():
    os.makedirs(FIG_DIR, exist_ok=True)

    ws = pd.read_csv(WORKSHEET)
    ws = ws[ws["similarity_rating_1to5"].astype(str).str.strip() != "-"].copy()
    ws["idx"] = ws["idx"].astype(int)
    ws["rating"] = ws["similarity_rating_1to5"].astype(int)
    print(f"[analyze] worksheet valid rows: {len(ws)}")

    voc = pd.read_csv(VOCAL_CSV)
    voc["idx"] = voc["idx"].astype(int)

    corpus = pd.read_csv(CORPUS_CSV)
    # corpus-wide z params for incongruence
    m_mode, s_mode = corpus["mode_score"].mean(), corpus["mode_score"].std(ddof=1)
    m_cent, s_cent = corpus["centroid"].mean(), corpus["centroid"].std(ddof=1)
    corpus_sub = corpus[["band", "idx", "mode_score", "centroid"]].copy()
    corpus_sub["idx"] = corpus_sub["idx"].astype(int)
    corpus_sub = corpus_sub.rename(columns={"mode_score": "mode_c", "centroid": "centroid_c"})

    def add_incongruence(df):
        df = df.merge(corpus_sub, on=["band", "idx"], how="left")
        zmode = (df["mode_c"] - m_mode) / s_mode
        zcent = (df["centroid_c"] - m_cent) / s_cent
        df["incongruence"] = np.abs(zmode - zcent)
        return df

    # ---- n=29 analysis frame ----
    df = ws.merge(voc.drop(columns=["song", "band"]), on="idx", how="left")
    df = add_incongruence(df)
    miss = df[NEW_FEATURES].isna().sum()
    print("[analyze] NaNs per new feature:\n", miss.to_string())
    n = len(df)

    y = df["rating"].values.astype(float)

    # ---- 1. baseline reproduction ----
    base_r2 = ols_r2(y, zscore_cols(df, BASELINE))

    # ---- 2/3/4. per-feature stats ----
    rows = []
    sp_p = []
    ctrl = zscore_cols(df, CONTROLS)
    y_res = residualize(y, ctrl)
    base_z = zscore_cols(df, BASELINE)
    for f in NEW_FEATURES:
        x = df[f].values.astype(float)
        rho, p_sp = stats.spearmanr(x, y)
        r_pe, p_pe = stats.pearsonr(x, y)
        # partial (residual method)
        x_res = residualize(x, ctrl)
        prho, pp_sp = stats.spearmanr(x_res, y_res)
        pr_pe, pp_pe = stats.pearsonr(x_res, y_res)
        # hierarchical dR2
        full = np.column_stack([base_z, (x - x.mean()) / x.std(ddof=1)])
        r2_full = ols_r2(y, full)
        dR2 = r2_full - base_r2
        # partial F p for increment (k_full predictors = 7)
        k_full = base_z.shape[1] + 1
        df2 = n - k_full - 1
        Fstat = (dR2 / 1.0) / ((1 - r2_full) / df2) if (1 - r2_full) > 0 and df2 > 0 else np.nan
        p_incr = 1 - stats.f.cdf(Fstat, 1, df2) if np.isfinite(Fstat) else np.nan
        rows.append({
            "feature": f, "spearman_rho": rho, "spearman_p": p_sp,
            "pearson_r": r_pe, "pearson_p": p_pe,
            "partial_spearman": prho, "partial_pearson": pr_pe,
            "dR2": dR2, "r2_full": r2_full, "p_incr": p_incr,
        })
        sp_p.append(p_sp)

    res = pd.DataFrame(rows)
    res["q_bh"] = bh_fdr(res["spearman_p"].values)

    # ---- 6. verdict ----
    def verdict(r):
        a = abs(r["spearman_rho"])
        ap = abs(r["partial_spearman"])
        if a >= 0.5 and r["spearman_p"] < 0.05 and ap >= 0.4:
            return "채택 후보"
        if 0.37 <= a < 0.5:
            return "시사적"
        return "기각"
    res["verdict"] = res.apply(verdict, axis=1)

    # ---- 7. anchors ----
    anc_rows = []
    for (band, idx), name in ANCHOR_IDX:
        r = voc[(voc["band"] == band) & (voc["idx"] == idx)].copy()
        r = add_incongruence(r)
        rec = {"anchor": name, "band": band, "idx": idx}
        for f in NEW_FEATURES:
            val = float(r[f].values[0])
            pct = stats.percentileofscore(df[f].values.astype(float), val, kind="mean")
            rec[f] = val
            rec[f + "_pct"] = pct
        anc_rows.append(rec)
    anc = pd.DataFrame(anc_rows)

    # ---- 8. scatter top-3 by |spearman| ----
    top3 = res.reindex(res["spearman_rho"].abs().sort_values(ascending=False).index).head(3)
    fig_files = []
    for _, r in top3.iterrows():
        f = r["feature"]
        fig, ax = plt.subplots(figsize=(5.2, 4.2))
        ax.scatter(df[f].values, y, s=45, edgecolor="black", alpha=0.8, color="#4C78A8")
        ax.set_xlabel(f, fontsize=11)
        ax.set_ylabel("similarity rating (1=most similar to esora, 5=least)", fontsize=9)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_title(f"{f} vs rating  (Spearman ρ={r['spearman_rho']:.3f}, p={r['spearman_p']:.3f})",
                     fontsize=9)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fp = os.path.join(FIG_DIR, f"scatter_{f}.png")
        fig.savefig(fp, dpi=130)
        plt.close(fig)
        fig_files.append(os.path.relpath(fp, HERE).replace("\\", "/"))

    # ---- write markdown ----
    def fmt(v, d=3):
        return "n/a" if (v is None or (isinstance(v, float) and not np.isfinite(v))) else f"{v:.{d}f}"

    lines = []
    lines.append("# Warmth/Pathos Vocal Feature Analysis — Results (n=29)\n")
    lines.append(f"- Analysis rows (labeled, idx97 excluded): **n={n}**")
    lines.append(f"- Anchors excluded from stats: esora(208), Sonorous(196), 天球(78)")
    lines.append(f"- Corpus for z-scores/incongruence: 660 songs "
                 f"(mode_score μ={m_mode:.4f} σ={s_mode:.4f}; centroid μ={m_cent:.2f} σ={s_cent:.2f})\n")

    lines.append("## 1. Baseline reproduction check\n")
    lines.append(f"6-feature baseline ({', '.join(BASELINE)}) OLS on rating:")
    lines.append(f"- **R² = {base_r2:.4f}**  (target 0.228, "
                 f"{'MATCH' if abs(base_r2 - 0.228) < 0.01 else 'MISMATCH'})\n")

    lines.append("## 2/3/4/5/6. Per-feature results\n")
    lines.append("| feature | Spearman ρ | p | q(BH) | Pearson r | partial ρ (Sp) | partial r (Pe) | ΔR² | verdict |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for _, r in res.iterrows():
        lines.append("| {f} | {rho} | {p} | {q} | {pe} | {prho} | {ppe} | {d} | {v} |".format(
            f=r["feature"], rho=fmt(r["spearman_rho"]), p=fmt(r["spearman_p"]),
            q=fmt(r["q_bh"]), pe=fmt(r["pearson_r"]), prho=fmt(r["partial_spearman"]),
            ppe=fmt(r["partial_pearson"]), d=fmt(r["dR2"], 4), v=r["verdict"]))
    lines.append("")
    lines.append("Notes: Spearman is the primary test; partial correlations control "
                 "mode_score + voiced_frac_mix (residual method). ΔR² = increment over the "
                 "6-feature baseline when the single feature is added (n=29, not all 9 together). "
                 "q = Benjamini-Hochberg FDR over the 9 Spearman p-values.\n")
    lines.append("Verdict rule: |Spearman ρ|≥0.5 (p<.05) AND |partial ρ|≥0.4 → 채택 후보; "
                 "0.37≤|ρ|<0.5 → 시사적; else 기각.\n")

    lines.append("### Hierarchical increment detail\n")
    lines.append("| feature | R²(base+feat) | ΔR² | p(increment F) |")
    lines.append("|---|---|---|---|")
    for _, r in res.iterrows():
        lines.append(f"| {r['feature']} | {fmt(r['r2_full'],4)} | {fmt(r['dR2'],4)} | {fmt(r['p_incr'])} |")
    lines.append("")

    lines.append("## 7. Anchor table (raw value + percentile within n=29)\n")
    header = "| feature | esora(208) | pct | Sonorous(196) | pct | 天球(78) | pct |"
    lines.append(header)
    lines.append("|---|---|---|---|---|---|---|")
    a0, a1, a2 = anc.iloc[0], anc.iloc[1], anc.iloc[2]
    for f in NEW_FEATURES:
        lines.append("| {f} | {v0} | {p0:.0f} | {v1} | {p1:.0f} | {v2} | {p2:.0f} |".format(
            f=f, v0=fmt(a0[f], 3), p0=a0[f + "_pct"],
            v1=fmt(a1[f], 3), p1=a1[f + "_pct"],
            v2=fmt(a2[f], 3), p2=a2[f + "_pct"]))
    lines.append("")

    lines.append("## 8. Scatter plots (top-3 by |Spearman ρ|)\n")
    for fp in fig_files:
        lines.append(f"![{fp}]({fp})")
    lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"[analyze] wrote {OUT_MD}")
    print(f"[analyze] figures: {fig_files}")

    # also echo the main table + baseline to stdout for the report
    print(f"\nBASELINE R2 = {base_r2:.4f}")
    print(res[["feature", "spearman_rho", "spearman_p", "q_bh",
               "partial_spearman", "dR2", "verdict"]].to_string(index=False))
    print("\nANCHORS:")
    print(anc[["anchor"] + NEW_FEATURES].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
