"""옥타브 오류군을 half(0.5x)/double(2x)로 나눠 method별 대표변수를 3그룹(correct 포함)
박스플롯으로 비교한다. 기타 비정수배 오차(2/3·3/2배 등, 4곡)는 표본이 너무 작고
half/double처럼 명확한 배율이 아니라서 이 플롯에서는 제외한다.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_METHOD12_DIR = Path(__file__).resolve().parent.parent
_TOPIC_DIR = _METHOD12_DIR.parent
_ALL_FEATURES_CSV = _TOPIC_DIR / "data" / "all_features.csv"
_BESTDORI_CSV = _TOPIC_DIR / "method-1-tempo" / "out" / "csv" / "tempo_bestdori_comparison.csv"

_OUT_CSV = _METHOD12_DIR / "out" / "csv" / "octave_class_comparison.csv"
_OUT_PNG = _METHOD12_DIR / "out" / "fig" / "octave_class_boxplots.png"

GROUPS = ["correct", "half(0.5x)", "double(2x)"]
COLORS = {"correct": "steelblue", "half(0.5x)": "goldenrod", "double(2x)": "indianred"}

REPRESENTATIVE_FEATURES = [
    (2, "m2-key_ks_confidence", "조성판정 신뢰도", "numeric"),
    (3, "m3-mode", "major/minor 비율", "categorical"),
    (4, "m4-lufs_integrated", "통합음량(LUFS)", "numeric"),
    (4, "m4-lra", "다이내믹기복(LRA)", "numeric"),
    (5, "m5-arousal_median", "각성도", "numeric"),
    (6, "m6-valence_median", "정서적 밝기", "numeric"),
    (7, "m7-danceability_norm", "리듬 규칙성", "numeric"),
    (8, "m8-acoustic_median", "어쿠스틱 확률", "numeric"),
    (9, "m9-instr_stem_ratio", "악기 에너지 비", "numeric"),
    (9, "m9-voice_median", "보컬 존재 확률", "numeric"),
    (10, "m10-crowd_median", "관중소음 확률", "numeric"),
    (11, "m11-speech_median", "음절밀도(4Hz 변조)", "numeric"),
    (11, "m11-vad_speech_ratio", "VAD speech 비율", "numeric"),
]


def main() -> None:
    feats = pd.read_csv(_ALL_FEATURES_CSV)
    bestdori = pd.read_csv(_BESTDORI_CSV)[["idx", "official_bpm", "ratio", "octave_class"]]
    df = bestdori.merge(feats, on="idx", how="left")

    df["group"] = np.where(
        df["ratio"].between(0.92, 1.08), "correct", df["octave_class"],
    )
    df = df[df["group"].isin(GROUPS)].copy()
    counts = df["group"].value_counts().reindex(GROUPS)
    print("그룹별 표본수:\n", counts)

    rows = []
    for _, col, label, kind in REPRESENTATIVE_FEATURES:
        if kind != "numeric":
            continue
        samples = [df.loc[df["group"] == g, col].dropna().values for g in GROUPS]
        if any(len(s) < 3 for s in samples):
            rows.append({"feature": col, "kruskal_p": np.nan, "note": "표본 부족"})
            continue
        h_stat, p = stats.kruskal(*samples)
        # half vs double 직접 대조(오류군 내부 비교)
        u_stat, p_hd = stats.mannwhitneyu(samples[1], samples[2], alternative="two-sided")
        rows.append({
            "feature": col,
            "median_correct": np.median(samples[0]),
            "median_half": np.median(samples[1]),
            "median_double": np.median(samples[2]),
            "kruskal_p(3그룹)": p,
            "half_vs_double_p": p_hd,
            "note": "",
        })
    result = pd.DataFrame(rows).sort_values("kruskal_p(3그룹)")
    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(_OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"저장: {_OUT_CSV}")
    print(result.to_string(index=False))

    n_panels = len(REPRESENTATIVE_FEATURES)
    ncols = 4
    nrows = int(np.ceil(n_panels / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 4.2 * nrows))
    axes = np.atleast_2d(axes)

    for i, (n, col, label, kind) in enumerate(REPRESENTATIVE_FEATURES):
        r, c = divmod(i, ncols)
        ax = axes[r][c]
        title = f"method-{n}. {label}\n({col})"

        if kind == "categorical":
            ct = pd.crosstab(df["group"], df[col], normalize="index").reindex(GROUPS)
            ct.plot(kind="bar", stacked=True, ax=ax, color=["#f4a259", "#5b7fb5"], legend=True)
            ax.set_xlabel("")
            ax.tick_params(axis="x", rotation=15)
            ax.legend(fontsize=7)
            ax.set_title(title, fontsize=8.5)
            continue

        samples = [df.loc[df["group"] == g, col].dropna().values for g in GROUPS]
        bp = ax.boxplot(samples, tick_labels=GROUPS, patch_artist=True)
        for box, g in zip(bp["boxes"], GROUPS):
            box.set_facecolor(COLORS[g])
        ax.tick_params(axis="x", rotation=15)

        row = result.loc[result["feature"] == col]
        p3 = row["kruskal_p(3그룹)"].values[0] if len(row) and pd.notna(row["kruskal_p(3그룹)"].values[0]) else float("nan")
        phd = row["half_vs_double_p"].values[0] if len(row) and "half_vs_double_p" in row and pd.notna(row["half_vs_double_p"].values[0]) else float("nan")
        sig = " *" if pd.notna(p3) and p3 < 0.05 else ""
        ax.set_title(f"{title}\nKruskal p={p3:.4f}{sig} | half-vs-double p={phd:.4f}", fontsize=8)

    for i in range(n_panels, nrows * ncols):
        r, c = divmod(i, ncols)
        axes[r][c].axis("off")

    fig.suptitle(
        f"correct(n={counts['correct']}) vs half(0.5x, n={counts['half(0.5x)']}) vs "
        f"double(2x, n={counts['double(2x)']}) — method별 대표변수 비교\n"
        "(기타 비정수배 오차 4곡은 표본 부족으로 제외)",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")


if __name__ == "__main__":
    main()
