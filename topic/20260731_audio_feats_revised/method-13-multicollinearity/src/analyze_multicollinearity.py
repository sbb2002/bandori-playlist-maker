from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_TOPIC_DIR = _METHOD_DIR.parent

ALL_FEATURES_CSV = _TOPIC_DIR / "data" / "all_features.csv"
OUT_CSV_DIR = _METHOD_DIR / "out" / "csv"
OUT_FIG_DIR = _METHOD_DIR / "out" / "fig"

# 사용가능 지표 (report_feats.md 2026-08-02 분류 기준)
CONTINUOUS_COLS = [
    "m4-lufs_integrated",
    "m4-lra",
    "m5-arousal_median",
    "m6-valence_median",
    "m7-danceability_norm",
    "m9-instr_stem_ratio",
    "m8-acoustic_median",
    "m11-speech_median",
]
MODE_COL = "m3-mode"


def compute_vif(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    X = df[cols].to_numpy(dtype=float)
    n, k = X.shape
    rows = []
    for i, col in enumerate(cols):
        y = X[:, i]
        others = np.delete(X, i, axis=1)
        others_with_const = np.column_stack([np.ones(n), others])
        coef, *_ = np.linalg.lstsq(others_with_const, y, rcond=None)
        y_pred = others_with_const @ coef
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot
        vif = 1 / (1 - r2) if r2 < 1 else np.inf
        rows.append({"feature": col, "r2_vs_rest": r2, "vif": vif})
    return pd.DataFrame(rows).sort_values("vif", ascending=False)


def main() -> None:
    df = pd.read_csv(ALL_FEATURES_CSV)

    df["m3-mode_bin"] = (df[MODE_COL] == "major").astype(float)
    # m1~m11 method 번호 순으로 정렬 (그림 가독성)
    analysis_cols = [
        "m3-mode_bin",
        "m4-lufs_integrated",
        "m4-lra",
        "m5-arousal_median",
        "m6-valence_median",
        "m7-danceability_norm",
        "m8-acoustic_median",
        "m9-instr_stem_ratio",
        "m11-speech_median",
    ]

    sub = df[analysis_cols].dropna()
    print(f"분석 대상 곡 수(결측 제거 후): {len(sub)} / {len(df)}")

    pearson = sub.corr(method="pearson")
    spearman = sub.corr(method="spearman")
    pearson.to_csv(OUT_CSV_DIR / "correlation_pearson.csv")
    spearman.to_csv(OUT_CSV_DIR / "correlation_spearman.csv")

    vif_df = compute_vif(sub, CONTINUOUS_COLS + ["m3-mode_bin"])
    vif_df.to_csv(OUT_CSV_DIR / "vif.csv", index=False)
    print(vif_df.to_string(index=False))

    fig, ax = plt.subplots(figsize=(9, 7.5))
    im = ax.imshow(pearson.to_numpy(), vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(analysis_cols)))
    ax.set_yticks(range(len(analysis_cols)))
    ax.set_xticklabels(analysis_cols, rotation=45, ha="right")
    ax.set_yticklabels(analysis_cols)
    for i in range(len(analysis_cols)):
        for j in range(len(analysis_cols)):
            val = pearson.to_numpy()[i, j]
            ax.text(
                j, i, f"{val:.2f}", ha="center", va="center",
                color="white" if abs(val) > 0.5 else "black", fontsize=8,
            )
    fig.colorbar(im, ax=ax, label="Pearson r")
    ax.set_title("사용가능 지표 상관행렬 (736곡)")
    fig.tight_layout()
    fig.savefig(OUT_FIG_DIR / "correlation_heatmap.png", dpi=150)
    print(f"저장: {OUT_FIG_DIR / 'correlation_heatmap.png'}")


if __name__ == "__main__":
    main()
