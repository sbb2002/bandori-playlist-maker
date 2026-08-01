"""tempo 옥타브 오차(31곡) vs 정답(542곡) 두 그룹을 method-2~11 지표로 비교.

새 오디오 추출 없음 — data/all_features.csv(method-1~11 병합)와
method-1-tempo/out/csv/tempo_bestdori_comparison.csv(Bestdori 대조)만 재사용.
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

_OUT_CSV = _METHOD12_DIR / "out" / "csv" / "octave_group_comparison.csv"
_OUT_PNG = _METHOD12_DIR / "out" / "fig" / "octave_group_boxplots.png"

# 두 그룹을 가르는 데 쓰는 컬럼(Bestdori 대조 결과, method-1) 자체는 비교 대상에서 제외.
NUMERIC_FEATURES = [
    "m2-key_ks_confidence",
    "m4-lra", "m4-lufs_integrated", "m4-st_median", "m4-st_p10", "m4-st_p90", "m4-st_std",
    "m5-arousal_median", "m5-arousal_p10", "m5-arousal_p90", "m5-arousal_std",
    "m6-valence_median", "m6-valence_p10", "m6-valence_p90", "m6-valence_std",
    "m7-dfa_alpha", "m7-danceability_norm", "m7-dfa_alpha_native", "m7-danceability_clf_prob",
    "m8-acoustic_median", "m8-acoustic_p10", "m8-acoustic_p90", "m8-acoustic_std",
    "m9-instr_stem_ratio", "m9-voice_median", "m9-voice_p10", "m9-voice_p90", "m9-voice_std",
    "m10-crowd_median", "m10-crowd_p10", "m10-crowd_p90", "m10-crowd_std", "m10-noise_floor_db",
    "m11-speech_median", "m11-speech_p10", "m11-speech_p90", "m11-speech_std", "m11-vad_speech_ratio",
]

BOOL_FEATURES = [
    "m1-halftime_flag", "m2-key_mismatch", "m2-mode_only_mismatch", "m2-modulation_flag",
    "m4-mastering_flag",
]

# 각 method가 내세우는 "대표값" 1~2개씩 — report_feats.md/각 method README 기준.
# (m1은 그룹을 나누는 기준 자체라 제외) method 번호 순서대로 정렬해서 그린다.
# kind="numeric" → 박스플롯, kind="categorical" → major/minor 비율 막대그래프(m3-mode 전용)
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


def _rank_biserial(a: np.ndarray, b: np.ndarray, u_stat: float) -> float:
    """Mann-Whitney U의 rank-biserial 상관계수(효과크기, -1~1)."""
    n1, n2 = len(a), len(b)
    return 1 - (2 * u_stat) / (n1 * n2)


def main() -> None:
    feats = pd.read_csv(_ALL_FEATURES_CSV)
    bestdori = pd.read_csv(_BESTDORI_CSV)[["idx", "official_bpm", "ratio", "octave_class"]]
    df = bestdori.merge(feats, on="idx", how="left")

    df["group"] = np.where(
        df["ratio"].between(0.92, 1.08), "correct",
        np.where(df["octave_class"].notna() | ~df["ratio"].between(0.92, 1.08), "octave_error", None),
    )
    # 8% 이내가 아니면 전부 오류군(half/double/기타 2·3배 포함)
    df["group"] = np.where(df["ratio"].between(0.92, 1.08), "correct", "octave_error")

    n_correct = (df["group"] == "correct").sum()
    n_error = (df["group"] == "octave_error").sum()
    print(f"correct={n_correct}, octave_error={n_error}")

    rows = []
    for col in NUMERIC_FEATURES:
        a = df.loc[df["group"] == "correct", col].dropna().values
        b = df.loc[df["group"] == "octave_error", col].dropna().values
        if len(a) < 5 or len(b) < 5 or np.std(a) == 0 and np.std(b) == 0:
            rows.append({"feature": col, "n_correct": len(a), "n_error": len(b),
                         "median_correct": np.median(a) if len(a) else np.nan,
                         "median_error": np.median(b) if len(b) else np.nan,
                         "p_value": np.nan, "effect_r": np.nan, "note": "분산 없음/표본 부족"})
            continue
        u_stat, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        r = _rank_biserial(a, b, u_stat)
        rows.append({
            "feature": col, "n_correct": len(a), "n_error": len(b),
            "median_correct": np.median(a), "median_error": np.median(b),
            "p_value": p, "effect_r": r, "note": "",
        })

    result = pd.DataFrame(rows).sort_values("p_value")
    bonferroni_alpha = 0.05 / len(NUMERIC_FEATURES)
    result["significant_raw(p<0.05)"] = result["p_value"] < 0.05
    result["significant_bonferroni"] = result["p_value"] < bonferroni_alpha

    # 불리언 플래그 — Fisher's exact
    bool_rows = []
    for col in BOOL_FEATURES:
        sub = df[[col, "group"]].dropna()
        ct = pd.crosstab(sub[col].astype(bool), sub["group"])
        if ct.shape != (2, 2):
            bool_rows.append({"feature": col, "note": "표 형태 이상(0/1 한쪽 없음)"})
            continue
        odds, p = stats.fisher_exact(ct.values)
        rate_correct = sub.loc[sub["group"] == "correct", col].astype(bool).mean()
        rate_error = sub.loc[sub["group"] == "octave_error", col].astype(bool).mean()
        bool_rows.append({
            "feature": col, "rate_correct": rate_correct, "rate_error": rate_error,
            "p_value": p, "odds_ratio": odds, "note": "",
        })
    bool_result = pd.DataFrame(bool_rows).sort_values("p_value")

    _OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(_OUT_CSV, index=False, encoding="utf-8-sig")
    bool_csv = _OUT_CSV.parent / "octave_group_bool_comparison.csv"
    bool_result.to_csv(bool_csv, index=False, encoding="utf-8-sig")
    print(f"저장: {_OUT_CSV}")
    print(f"저장: {bool_csv}")

    print()
    print("=== 수치형 지표 (p-value 오름차순) ===")
    print(result.to_string(index=False))
    print()
    print("=== 불리언 플래그 ===")
    print(bool_result.to_string(index=False))

    # --- 각 method 대표변수 박스플롯(method 번호 순서대로) ---
    n_panels = len(REPRESENTATIVE_FEATURES)
    ncols = 4
    nrows = int(np.ceil(n_panels / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.4 * ncols, 4.2 * nrows))
    axes = np.atleast_2d(axes)

    for i, (n, col, label, kind) in enumerate(REPRESENTATIVE_FEATURES):
        r, c = divmod(i, ncols)
        ax = axes[r][c]
        title = f"method-{n}. {label}\n({col})"

        if kind == "categorical":
            ct = pd.crosstab(df["group"], df[col], normalize="index").reindex(["correct", "octave_error"])
            ct.plot(kind="bar", stacked=True, ax=ax, color=["#f4a259", "#5b7fb5"], legend=True)
            ax.set_xlabel("")
            ax.tick_params(axis="x", rotation=0)
            ax.legend(fontsize=7)
            ax.set_title(title, fontsize=8.5)
            continue

        a = df.loc[df["group"] == "correct", col].dropna().values
        b = df.loc[df["group"] == "octave_error", col].dropna().values
        bp = ax.boxplot([a, b], tick_labels=["correct", "octave_error"], patch_artist=True)
        bp["boxes"][0].set_facecolor("steelblue")
        bp["boxes"][1].set_facecolor("indianred")
        row = result.loc[result["feature"] == col]
        p = row["p_value"].values[0] if len(row) and pd.notna(row["p_value"].values[0]) else float("nan")
        sig = " *" if pd.notna(p) and p < 0.05 else ""
        ax.set_title(f"{title} p={p:.4f}{sig}", fontsize=8.5)

    for i in range(n_panels, nrows * ncols):
        r, c = divmod(i, ncols)
        axes[r][c].axis("off")

    fig.suptitle("정답군(correct) vs 옥타브오류군(octave_error) — method별 대표변수 비교", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")


if __name__ == "__main__":
    main()
