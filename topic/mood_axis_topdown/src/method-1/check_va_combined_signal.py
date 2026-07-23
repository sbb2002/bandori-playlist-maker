"""GEMS-9 n=1 파일럿(35곡) x V-A(mode_score, energy_full) 조합 신호 확인.

배경: screen_candidate_signals.py는 피쳐를 하나씩만 검정하므로, V(valence 대리
지표 mode_score)와 A(arousal 대리 지표 energy_full)를 억제효과(suppression effect)로
조합해야만 드러나는 신호를 구조적으로 못 잡는다. 이 스크립트는 wonder/transcendence/
power/sadness(단독 스크리닝 미통과 4항목)를 대상으로:
1. V, A 단독 Spearman 상관(기존 스크리닝과 동일 — 대조용).
2. V, A 편상관(partial correlation) — 서로를 통제했을 때 순수 기여도.
3. 다중회귀 R^2(참고용, statsmodels 없이 numpy로 직접 계산).
4. V/A 중앙값 기준 사분면 평균 — 방향성 확인용.

n=35, 탐색적 분석(사전 다중비교 보정 없음) — report/03 §주의 참고.
"""
import csv
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr, spearmanr, t as tdist

ROOT = Path(__file__).resolve().parents[4]
GEMS_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "gems9_pilot_candidates.csv"
AUDIO_FEATS_PATH = ROOT / "topic" / "audio_feats_analysis" / "out" / "audio_feats.csv"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "va_combined_signal_check.csv"

TARGET_ITEMS = ["wonder", "transcendence", "power", "sadness"]


def load_merged():
    gems_rows = list(csv.DictReader(open(GEMS_PATH, encoding="utf-8-sig")))
    audio_by_idx = {}
    with open(AUDIO_FEATS_PATH, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            idx_raw = (r.get("idx") or "").strip()
            if not idx_raw:
                continue
            audio_by_idx[int(float(idx_raw))] = r

    idxs, items_vals, V, A = [], {k: [] for k in TARGET_ITEMS}, [], []
    for r in gems_rows:
        idx = int(r["idx"])
        a = audio_by_idx.get(idx)
        if a is None:
            continue
        mode_score = (a.get("mode_score") or "").strip()
        energy_full = (a.get("energy_full") or "").strip()
        if mode_score == "" or energy_full == "":
            continue
        idxs.append(idx)
        V.append(float(mode_score))
        A.append(float(energy_full))
        for k in TARGET_ITEMS:
            items_vals[k].append(float(r[k]))

    return idxs, items_vals, np.array(V), np.array(A)


def partial_corr(y, x, z):
    """y, x를 z에 회귀시켜 residual끼리 상관 — z를 통제한 x-y 순수 상관."""
    Z = np.column_stack([np.ones_like(z), z])
    by, *_ = np.linalg.lstsq(Z, y, rcond=None)
    bx, *_ = np.linalg.lstsq(Z, x, rcond=None)
    ry = y - Z @ by
    rx = x - Z @ bx
    return pearsonr(rx, ry)


def multiple_r2(y, X):
    n = len(y)
    Xd = np.column_stack([np.ones(n), X])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    yhat = Xd @ beta
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    return 1 - ss_res / ss_tot


def main():
    idxs, items_vals, V, A = load_merged()
    print(f"GEMS x audio_feats 병합 n = {len(idxs)}")

    rows = []
    for item in TARGET_ITEMS:
        y = np.array(items_vals[item])

        rho_v, p_v = spearmanr(y, V)
        rho_a, p_a = spearmanr(y, A)
        pr_v, pp_v = partial_corr(y, V, A)
        pr_a, pp_a = partial_corr(y, A, V)
        r2 = multiple_r2(y, np.column_stack([V, A]))

        vmed, amed = np.median(V), np.median(A)
        quad_hh = y[(V >= vmed) & (A >= amed)].mean()
        quad_hl = y[(V >= vmed) & (A < amed)].mean()
        quad_lh = y[(V < vmed) & (A >= amed)].mean()
        quad_ll = y[(V < vmed) & (A < amed)].mean()

        rows.append({
            "gems_item": item,
            "rho_V": rho_v, "p_V": p_v,
            "rho_A": rho_a, "p_A": p_a,
            "partial_r_V_given_A": pr_v, "partial_p_V_given_A": pp_v,
            "partial_r_A_given_V": pr_a, "partial_p_A_given_V": pp_a,
            "r2_multiple": r2,
            "quad_highV_highA": quad_hh, "quad_highV_lowA": quad_hl,
            "quad_lowV_highA": quad_lh, "quad_lowV_lowA": quad_ll,
        })
        print(
            f"{item:15s} rho_V={rho_v:+.3f}(p={p_v:.3f}) rho_A={rho_a:+.3f}(p={p_a:.3f})  "
            f"partial_V|A={pr_v:+.3f}(p={pp_v:.3f}) partial_A|V={pr_a:+.3f}(p={pp_a:.3f})  "
            f"R2={r2:.3f}"
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"-> {OUT_PATH}")


if __name__ == "__main__":
    main()
