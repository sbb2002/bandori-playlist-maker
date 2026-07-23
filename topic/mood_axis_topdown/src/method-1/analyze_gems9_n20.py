"""GEMS-9 n>=20 라운드 분석 파이프라인 — 통계 자문(report/04) 반영판.

실행 흐름(응답 데이터가 모이면):
1. 응답(rater_id, song_idx, GEMS 9항목) 로드.
2. 각 GEMS 항목마다 "고정효과 rater + 랜덤절편 song" 혼합모형으로 평정자 주효과를 제거한
   곡별 조정점수(song BLUP)를 뽑는다.
   - 주의: 정식 `(1|song)+(1|rater)` crossed 랜덤효과가 아니라 rater를 고정효과로 둔
     간소화판이다. 목적이 "특정 22명의 평정자 population에 일반화"가 아니라 "이 22명이
     남긴 평정자 개인차(nuisance)를 곡 점수에서 제거"하는 것이므로 이 간소화가 타당하다
     (자문위원이 언급한 가법성 가정 그대로 유지, crossed-effect 구현 리스크는 회피).
3. 곡별 inclusion_prob(gems9_n20_candidates.csv)의 역수를 가중치로 쓰는 가중 Spearman을
   대표 피쳐(gems9_n20_representative_features.csv) 전부와 계산.
4. 부트스트랩(응답자 단위 재표집 -> 혼합모형 재적합 -> BLUP 재산출 -> 가중 Spearman 재계산)
   으로 rho의 신뢰구간을 산출 — BLUP을 "알려진 값"처럼 취급해 교과서 공식으로 CI를 내면
   과소추정된다는 자문위원의 must-fix 반영.
5. GEMS 항목별 BH-FDR 다중비교 보정.
6. (홀드아웃 채점 완료 후) confirmatory_check()로 재현 여부 판정 — "재유의"가 아니라
   부호일치 + CI 겹침 + 실용 효과크기(|rho|>=0.3) 유지로 판정(자문위원 지적 반영).

실제 n>=20 응답 데이터가 아직 없으므로, 이 스크립트를 그대로 실행하면 합성(synthetic)
데이터로 파이프라인 동작만 검증하는 스모크테스트가 돈다(진짜 결과 아님, 로그에 명시됨).
"""
import csv
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import t as tdist

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "out"
CANDIDATES_PATH = OUT_DIR / "gems9_n20_candidates.csv"
REP_FEATURES_PATH = OUT_DIR / "gems9_n20_representative_features.csv"
AUDIO_FEATS_PATH = OUT_DIR.parent.parent / "audio_feats_analysis" / "out" / "audio_feats.csv"
RESPONSES_PATH = OUT_DIR / "gems9_n20_responses.csv"  # 실제 응답 수집 후 이 경로에 저장

GEMS_ITEMS = [
    "wonder", "transcendence", "tenderness", "nostalgia", "peacefulness",
    "power", "joyful_activation", "tension", "sadness",
]

PASS_RHO = 0.4
PASS_Q = 0.05
CONFIRM_RHO = 0.3
N_BOOTSTRAP = 500
SEED = 20260723


def bh_fdr(pvals):
    idx_valid = [i for i, p in enumerate(pvals) if p == p]
    m = len(idx_valid)
    q = [float("nan")] * len(pvals)
    if m == 0:
        return q
    order = sorted(idx_valid, key=lambda i: pvals[i])
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        real_rank = m - rank + 1
        val = pvals[i] * m / real_rank
        prev = min(prev, val)
        q[i] = prev
    return q


def weighted_rank(x, w):
    """가중 중간순위(mid-rank). 동률은 평균 순위."""
    x = np.asarray(x, dtype=float)
    w = np.asarray(w, dtype=float)
    order = np.argsort(x, kind="mergesort")
    n = len(x)
    ranks = np.zeros(n)
    i = 0
    cum = 0.0
    while i < n:
        j = i
        while j + 1 < n and x[order[j + 1]] == x[order[i]]:
            j += 1
        w_before = cum
        w_tie = w[order[i:j + 1]].sum()
        tie_rank = w_before + w_tie / 2.0
        ranks[order[i:j + 1]] = tie_rank
        cum += w_tie
        i = j + 1
    return ranks


def weighted_pearson(x, y, w):
    w = np.asarray(w, dtype=float)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    wsum = w.sum()
    mx = (w * x).sum() / wsum
    my = (w * y).sum() / wsum
    cov = (w * (x - mx) * (y - my)).sum() / wsum
    vx = (w * (x - mx) ** 2).sum() / wsum
    vy = (w * (y - my) ** 2).sum() / wsum
    if vx <= 0 or vy <= 0:
        return float("nan")
    return cov / np.sqrt(vx * vy)


def weighted_spearman(x, y, w):
    rx = weighted_rank(x, w)
    ry = weighted_rank(y, w)
    return weighted_pearson(rx, ry, w)


def song_adjusted_scores(responses, item):
    """score ~ C(rater) + (1|song) 적합 -> 곡별 조정점수(랜덤절편 + 고정절편) 반환."""
    df = responses[["rater_id", "song_idx", item]].dropna().copy()
    df["rater_id"] = df["rater_id"].astype(str)
    df["song_idx"] = df["song_idx"].astype(int)

    model = smf.mixedlm(f"{item} ~ C(rater_id)", data=df, groups=df["song_idx"])
    result = model.fit(reml=True)

    intercept = result.fe_params.get("Intercept", 0.0)
    re = result.random_effects  # {song_idx: Series(['Group']=...)}
    song_scores = {
        song: intercept + re[song].iloc[0]
        for song in re
    }
    return pd.Series(song_scores, name=item)


def bootstrap_rho_ci(responses, candidates, item, feature_cols, n_boot=N_BOOTSTRAP, seed=SEED,
                      use_weight=True):
    """use_weight=False -> 비가중(균등가중) 부트스트랩. 2026-07-23 밴드당 동일 N 전환 이후
    비가중이 주분석(장르균등대표), 가중은 '카탈로그 비례였다면'을 보는 보조체크로 역할이
    바뀌었다(report/04 §3-2)."""
    rng = np.random.default_rng(seed)
    raters = responses["rater_id"].unique()
    boot_rhos = {f: [] for f in feature_cols}

    for _ in range(n_boot):
        sampled_raters = rng.choice(raters, size=len(raters), replace=True)
        parts = [responses[responses["rater_id"] == r] for r in sampled_raters]
        boot_df = pd.concat(parts, ignore_index=True)
        # 재표집으로 어떤 랜덤 반복본에서 특정 곡이 통째로 빠질 수 있음 -> 해당 곡은 그 반복에서 제외
        try:
            scores = song_adjusted_scores(boot_df, item)
        except Exception:
            continue
        merged = candidates.set_index("idx").join(scores, how="inner")
        if len(merged) < 10:
            continue
        w = merged["weight"] if use_weight else pd.Series(1.0, index=merged.index)
        for feat in feature_cols:
            rho = weighted_spearman(merged[feat], merged[item], w)
            boot_rhos[feat].append(rho)

    ci = {}
    for feat in feature_cols:
        vals = np.array([v for v in boot_rhos[feat] if v == v])
        if len(vals) < n_boot * 0.5:
            ci[feat] = (float("nan"), float("nan"))
        else:
            ci[feat] = (np.percentile(vals, 2.5), np.percentile(vals, 97.5))
    return ci


def kish_design_effect(weights):
    """가중치 불균등으로 인한 유효표본 손실(Kish deff). eff_n = n/deff."""
    w = np.asarray(weights, dtype=float)
    n = len(w)
    deff = n * np.sum(w ** 2) / (np.sum(w) ** 2)
    return deff, n / deff


BAND_ETA2_MIN = 0.0  # 참고용(§6 태깅), 판정에는 안 씀
PARTIAL_RHO_MIN = 0.2       # notes/n20_prereg.md §8
LEAVEOUT_RHO_MIN = CONFIRM_RHO  # 0.3, 2단계 확증과 동일 기준 재사용
TOP_N_BANDS_EXCLUDE = 2


def weighted_ols_residual(y, band, w):
    """y ~ C(band) 가중회귀 잔차 -> 밴드 평균차를 제거한 값(밴드 내 편차만 남음)."""
    y = np.asarray(y, dtype=float)
    w = np.asarray(w, dtype=float)
    dummies = pd.get_dummies(pd.Series(band), drop_first=False).to_numpy(dtype=float)
    sw = np.sqrt(w)
    X = dummies * sw[:, None]
    Y = y * sw
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    fitted = dummies @ beta
    return y - fitted


def band_eta_squared(feature_values, band):
    """피쳐 분산 중 밴드로 설명되는 비율(R^2 of feature ~ C(band))."""
    y = np.asarray(feature_values, dtype=float)
    dummies = pd.get_dummies(pd.Series(band), drop_first=False).to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(dummies, y, rcond=None)
    fitted = dummies @ beta
    ss_res = np.sum((y - fitted) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")


def band_bias_diagnostics(merged, item, feat, top_bands):
    """notes/n20_prereg.md §8: 밴드 통제 편상관 + 최대밴드 제외 재계산 + 개별 플래그 판정.

    2026-07-23 밴드당 동일 N 전환 이후 주분석이 비가중이므로, 여기서도 비가중(균등가중)을
    써서 run_main_analysis의 주 rho와 같은 기준으로 비교한다(가중 쓰면 서로 다른 기준을
    비교하는 셈이라 sign_flip 판정이 왜곡될 수 있음)."""
    x = merged[feat].to_numpy(dtype=float)
    y = merged[item].to_numpy(dtype=float)
    w = np.ones(len(merged))
    band = merged["band"].to_numpy()

    marginal_rho = weighted_spearman(x, y, w)

    resid_x = weighted_ols_residual(x, band, w)
    resid_y = weighted_ols_residual(y, band, w)
    partial_rho = weighted_pearson(resid_x, resid_y, w)

    keep = ~np.isin(band, top_bands)
    if keep.sum() >= 10:
        leaveout_rho = weighted_spearman(x[keep], y[keep], w[keep])
    else:
        leaveout_rho = float("nan")

    eta2 = band_eta_squared(x, band)

    sign_flip_partial = (partial_rho == partial_rho) and (marginal_rho * partial_rho < 0)
    weak_partial = (partial_rho == partial_rho) and (abs(partial_rho) < PARTIAL_RHO_MIN)
    sign_flip_leaveout = (leaveout_rho == leaveout_rho) and (marginal_rho * leaveout_rho < 0)
    weak_leaveout = (leaveout_rho == leaveout_rho) and (abs(leaveout_rho) < LEAVEOUT_RHO_MIN)

    flagged = sign_flip_partial or weak_partial or sign_flip_leaveout or weak_leaveout
    return {
        "band_eta2": eta2,
        "partial_rho_band_controlled": partial_rho,
        "leaveout_rho_top2bands_excluded": leaveout_rho,
        "band_dependent_flag": bool(flagged),
    }


def confirmatory_check(main_rho, main_ci, holdout_rho, holdout_ci, threshold=CONFIRM_RHO):
    """자문위원 지적 반영: '재유의'가 아니라 부호일치 + CI 겹침 + 실용효과크기 유지로 판정."""
    if any(v != v for v in (main_rho, holdout_rho, *main_ci, *holdout_ci)):
        return {"pass": False, "reason": "nan"}
    sign_match = (main_rho > 0) == (holdout_rho > 0)
    ci_overlap = not (main_ci[1] < holdout_ci[0] or holdout_ci[1] < main_ci[0])
    effect_retained = abs(holdout_rho) >= threshold
    passed = sign_match and ci_overlap and effect_retained
    return {
        "pass": passed, "sign_match": sign_match,
        "ci_overlap": ci_overlap, "effect_retained": effect_retained,
    }


def load_representative_features():
    with open(REP_FEATURES_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [r["feature"] for r in rows if r["is_representative"] == "True"]


def load_candidates_with_features():
    candidates = pd.read_csv(CANDIDATES_PATH, encoding="utf-8-sig")
    audio = pd.read_csv(AUDIO_FEATS_PATH, encoding="utf-8")
    feature_cols = load_representative_features()
    merged = candidates.merge(audio[["idx"] + feature_cols], on="idx", how="left")
    merged["weight"] = 1.0 / merged["inclusion_prob"]
    return merged, feature_cols


def run_main_analysis(responses):
    """2026-07-23 밴드당 동일 N 전환 이후 주분석은 '비가중'(장르균등대표, EQUAL_N_PER_BAND과
    일치)이다. 가중(포함확률 역수) 버전은 '이 결과가 카탈로그 비례 표본이었다면 어땠을까'를
    보는 보조체크로만 병기한다(rho/ci/pass는 비가중 기준, *_weighted 컬럼은 참고용)."""
    candidates, feature_cols = load_candidates_with_features()
    results = []
    for item in GEMS_ITEMS:
        scores = song_adjusted_scores(responses, item)
        merged = candidates.set_index("idx").join(scores, how="inner").reset_index()
        ci_unw = bootstrap_rho_ci(responses, candidates, item, feature_cols,
                                   n_boot=N_BOOTSTRAP, use_weight=False)
        ci_w = bootstrap_rho_ci(responses, candidates, item, feature_cols,
                                 n_boot=N_BOOTSTRAP, use_weight=True)

        pvals = []
        rows_this_item = []
        unit_w = pd.Series(1.0, index=merged.index)
        for feat in feature_cols:
            rho = weighted_spearman(merged[feat], merged[item], unit_w)  # 주분석: 비가중
            rho_weighted = weighted_spearman(merged[feat], merged[item], merged["weight"])
            lo, hi = ci_unw[feat]
            lo_w, hi_w = ci_w[feat]
            # 부트스트랩 CI로부터 근사 p값(정규근사, 참고용 — 주 판정은 CI 자체로 함)
            se = (hi - lo) / (2 * 1.96) if hi == hi and lo == lo else float("nan")
            z = rho / se if se and se == se and se > 0 else float("nan")
            p = 2 * (1 - tdist.cdf(abs(z), df=len(merged) - 2)) if z == z else float("nan")
            rows_this_item.append({
                "gems_item": item, "feature": feat, "n": len(merged),
                "rho": rho, "ci_lo": lo, "ci_hi": hi, "p_approx": p,
                "rho_weighted": rho_weighted, "ci_lo_weighted": lo_w, "ci_hi_weighted": hi_w,
            })
            pvals.append(p)

        qs = bh_fdr([r["p_approx"] for r in rows_this_item])
        # 2026-07-23 밴드당 동일 N 전환 이후: 표본 곡수는 전 밴드 동률(예: 7곡)이라
        # value_counts()로는 더 이상 "영향력 큰 밴드"를 못 고른다. 가중치(=포함확률 역수,
        # 곧 밴드 모집단 크기에 비례)가 가장 큰 2개 밴드를 대신 고른다 -> 여전히
        # poppin_party/roselia처럼 카탈로그 비중이 큰 밴드를 가리킨다.
        top_bands = (
            candidates.groupby("band")["weight"].mean()
            .nlargest(TOP_N_BANDS_EXCLUDE).index.tolist()
        )
        for r, q in zip(rows_this_item, qs):
            r["q_bh"] = q
            r["pass"] = bool(
                r["rho"] == r["rho"] and abs(r["rho"]) >= PASS_RHO and q == q and q < PASS_Q
            )
            diag = band_bias_diagnostics(merged, item, r["feature"], top_bands)
            r.update(diag)
            results.append(r)
    return pd.DataFrame(results)


def band_redesign_recommendation(results):
    """notes/n20_prereg.md §8: 1차 통과 피쳐 중 과반수가 밴드 의존적으로 플래그되면
    밴드당 동일 N으로 재설계할 것을 권고."""
    passed = results[results["pass"]]
    if len(passed) == 0:
        return {"n_passed": 0, "n_flagged": 0, "majority_flagged": False}
    n_flagged = int(passed["band_dependent_flag"].sum())
    majority = n_flagged / len(passed) > 0.5
    return {"n_passed": len(passed), "n_flagged": n_flagged, "majority_flagged": majority}


def make_synthetic_responses(candidates, n_raters=22, seed=SEED):
    """실제 응답 데이터가 없을 때 파이프라인 배선 확인용 합성 데이터.
    real GEMS 관계를 흉내내지 않는 순수 노이즈 + 약한 신호이므로 결과 해석 금지."""
    rng = np.random.default_rng(seed)
    rows = []
    rater_bias = {f"R{i}": rng.normal(0, 0.5) for i in range(n_raters)}
    song_true = {idx: rng.normal(0, 1) for idx in candidates["idx"]}
    for idx in candidates["idx"]:
        raters = rng.choice(list(rater_bias), size=8, replace=False)
        for r in raters:
            for item in GEMS_ITEMS:
                val = 3 + 0.6 * song_true[idx] + rater_bias[r] + rng.normal(0, 0.8)
                rows.append({"rater_id": r, "song_idx": idx, item: float(np.clip(val, 1, 5))})
    df = pd.DataFrame(rows)
    return df.groupby(["rater_id", "song_idx"], as_index=False).first()


def main():
    global N_BOOTSTRAP
    candidates, _ = load_candidates_with_features()
    deff, eff_n = kish_design_effect(candidates["weight"])
    print(f"[가중치 설계효과] Kish deff={deff:.3f}, 가중(카탈로그 보조체크) 유효표본"
          f" ≈ {eff_n:.1f}/{len(candidates)} — 주분석(비가중)의 유효표본은 이 손실과 무관\n")

    if RESPONSES_PATH.exists():
        responses = pd.read_csv(RESPONSES_PATH, encoding="utf-8-sig")
        print(f"실제 응답 로드: {RESPONSES_PATH} ({len(responses)}행)")
        synthetic = False
    else:
        print("[스모크테스트 모드] 실제 응답 파일이 없어 합성 데이터로 파이프라인만 검증합니다.")
        print("이 결과는 진짜 GEMS-피쳐 관계가 아닙니다 — 배선(코드 동작) 확인용입니다.")
        print("(스모크테스트는 부트스트랩 반복수를 20으로 줄여 빠르게 돕니다. 실제 분석 시엔")
        print(f" 응답 CSV를 {RESPONSES_PATH}에 두면 N_BOOTSTRAP={N_BOOTSTRAP}로 정식 실행됩니다.)\n")
        responses = make_synthetic_responses(candidates)
        synthetic = True
        N_BOOTSTRAP = 20

    results = run_main_analysis(responses)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / ("gems9_n20_analysis_SMOKETEST.csv" if synthetic else "gems9_n20_analysis_results.csv")
    results.sort_values("rho", key=lambda s: -s.abs()).to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"-> {out_path} ({len(results)}행)")

    passed = results[results["pass"]]
    print(f"\n통과(|rho|>={PASS_RHO}, q<{PASS_Q}): {len(passed)}건")
    for _, r in passed.iterrows():
        flag = " [밴드의존 플래그]" if r["band_dependent_flag"] else ""
        print(f"  {r['gems_item']:20s} x {r['feature']:16s} rho={r['rho']:+.3f} "
              f"CI=[{r['ci_lo']:.3f},{r['ci_hi']:.3f}] q={r['q_bh']:.3f}{flag}")

    rec = band_redesign_recommendation(results)
    print(f"\n[밴드 편중 판정] 통과 {rec['n_passed']}건 중 {rec['n_flagged']}건 밴드의존 플래그")
    if rec["majority_flagged"]:
        print("-> 과반수 플래그됨: 밴드당 동일 N으로도 특정 밴드 의존성이 강함 — 원인 추가 조사 필요")
    else:
        print("-> 과반수 미만: 현재 밴드당 동일 N 설계 유지, 플래그된 피쳐만 한계로 명시")

    if synthetic:
        print("\n[스모크테스트] 파이프라인이 에러 없이 끝까지 돌았는지만 확인하십시오.")


if __name__ == "__main__":
    main()
