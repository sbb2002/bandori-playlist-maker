"""§3 후보 신호 전수 스크리닝 — GEMS-9 n=1 파일럿(35곡) x 기존 오디오/보컬 피쳐.

framework.md §3 절차:
1. GEMS-9 라벨(out/gems9_pilot_candidates.csv)과 기존 후보 신호를 전부 한 번에 대조.
2. 축(GEMS 9항목) x 후보신호 매트릭스, Spearman rho + 유의성.
3. 피쳐 신뢰도 등급(Tier 1/2/3, framework.md §3a) 적용 — Tier 3은 스크리닝 자체에서 제외.
4. 통과 기준(§3c): |rho| >= 0.4 AND BH-FDR 보정 후 유의(q < 0.05).
   다중비교 보정은 축(GEMS 항목)마다 그 축에 돌린 신호 개수 기준으로 적용한다.
"""
import csv
from pathlib import Path

from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[4]
GEMS_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "gems9_pilot_candidates.csv"
AUDIO_FEATS_PATH = ROOT / "topic" / "audio_feats_analysis" / "out" / "audio_feats.csv"
VOCAL_PATH = ROOT / "topic" / "mood_warmth" / "vocal_features_full.csv"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "screening_results.csv"

GEMS_ITEMS = [
    "wonder", "transcendence", "tenderness", "nostalgia", "peacefulness",
    "power", "joyful_activation", "tension", "sadness",
]

# framework.md §3a 피쳐 신뢰도 등급. Tier 3은 아예 후보에서 뺀다.
TIER1 = [
    "mfcc_1_mean", "mfcc_2_mean", "mfcc_3_mean", "mfcc_4_mean", "mfcc_5_mean",
    "mfcc_6_mean", "mfcc_7_mean", "mfcc_8_mean", "mfcc_9_mean", "mfcc_10_mean",
    "mfcc_11_mean", "mfcc_12_mean", "mfcc_13_mean",
    "contrast_mean", "energy_full", "rms_mean", "bpm",
]
TIER2 = ["mode_score", "tempo_bpm"]
# vocal_features_full.csv 후보 — audio_feats.csv엔 없는 별도 소스. GEMS 35곡과 overlap이
# 작아(§ 실행 로그 참고) 참고용으로만 돌리고 Tier1/2와 같은 반열로 취급하지 않는다.
VOCAL_CANDIDATES = [
    "jitter_local", "shimmer_local", "hnr_mean",
    "f0_median_st", "f0_range_st", "f0_std_st", "vocal_centroid",
]

PASS_RHO = 0.4
PASS_Q = 0.05
MIN_N = 10  # 이 미만이면 상관계수를 내도 스크리닝 판정에 못 씀(참고치로만 표시)


def bh_fdr(pvals):
    """Benjamini-Hochberg. NaN은 건드리지 않고 그대로 반환."""
    idx_valid = [i for i, p in enumerate(pvals) if p == p]  # NaN 제외
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


def load_gems():
    rows = list(csv.DictReader(open(GEMS_PATH, encoding="utf-8-sig")))
    by_idx = {}
    for r in rows:
        idx = int(r["idx"])
        scores = {}
        ok = True
        for item in GEMS_ITEMS:
            v = (r.get(item) or "").strip()
            if not v:
                ok = False
                break
            scores[item] = float(v)
        if ok:
            by_idx[idx] = scores
    return by_idx


def load_numeric_csv(path, candidate_cols):
    by_idx = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            idx_raw = (r.get("idx") or "").strip()
            if not idx_raw:
                continue
            idx = int(float(idx_raw))
            vals = {}
            for c in candidate_cols:
                raw = (r.get(c) or "").strip()
                if raw == "" or raw.lower() == "nan":
                    continue
                try:
                    vals[c] = float(raw)
                except ValueError:
                    continue
            if vals:
                by_idx[idx] = vals
    return by_idx


def run_block(gems, feats, candidates, tier_label, results):
    for item in GEMS_ITEMS:
        pvals = []
        rows_this_item = []
        for cand in candidates:
            pairs = [
                (gems[idx][item], feats[idx][cand])
                for idx in gems
                if idx in feats and cand in feats[idx]
            ]
            n = len(pairs)
            if n < 3:
                continue
            xs, ys = zip(*pairs)
            rho, p = spearmanr(xs, ys)
            rows_this_item.append({
                "gems_item": item, "candidate": cand, "tier": tier_label,
                "n": n, "rho": rho, "p": p,
            })
            pvals.append(p)
        qs = bh_fdr([r["p"] for r in rows_this_item])
        for r, q in zip(rows_this_item, qs):
            r["q_bh"] = q
            r["pass"] = bool(
                r["n"] >= MIN_N and abs(r["rho"]) >= PASS_RHO and q == q and q < PASS_Q
            )
            results.append(r)


def main():
    gems = load_gems()
    print(f"GEMS-9 채점 완료곡: {len(gems)}곡")

    audio = load_numeric_csv(AUDIO_FEATS_PATH, TIER1 + TIER2)
    vocal = load_numeric_csv(VOCAL_PATH, VOCAL_CANDIDATES)
    print(f"audio_feats.csv 중 GEMS와 겹치는 곡: {len(set(gems) & set(audio))}")
    print(f"vocal_features_full.csv 중 GEMS와 겹치는 곡: {len(set(gems) & set(vocal))}")

    results = []
    run_block(gems, audio, TIER1, "Tier1", results)
    run_block(gems, audio, TIER2, "Tier2", results)
    run_block(gems, vocal, VOCAL_CANDIDATES, "Vocal(참고, n작음)", results)

    results.sort(key=lambda r: (-abs(r["rho"]) if r["rho"] == r["rho"] else 0))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["gems_item", "candidate", "tier", "n", "rho", "p", "q_bh", "pass"])
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"-> {OUT_PATH} ({len(results)}행)")

    passed = [r for r in results if r["pass"]]
    print(f"\n통과(|rho|>=.4, n>={MIN_N}, BH-FDR q<{PASS_Q}): {len(passed)}건")
    for r in passed:
        print(f"  {r['gems_item']:20s} x {r['candidate']:16s} ({r['tier']:6s}) rho={r['rho']:+.3f} n={r['n']} q={r['q_bh']:.3f}")


if __name__ == "__main__":
    main()
