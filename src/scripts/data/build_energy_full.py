"""전곡 서브피처 → 복합(composite) `energy_full` 산출·검증·병합 스크립트.

`extract_full_energy.py`가 뽑은 `data/full_audio_features.csv`(원시 서브피처)를 받아:
  1. 그라운드트루스(조용/시끄러움/오판곡)로 각 피처의 분리력을 정량 평가(AUC·Cohen's d),
  2. 검증된 복합 강도(intensity)를 선정,
  3. eligible 풀(653곡) 기준 백분위로 0~1 정규화 → `energy_full`,
  4. 문제곡 before/after 순위·분리도를 출력,
  5. (--write 시) `data/songs_master.csv`에 `energy_full` 컬럼을 병합(기존 컬럼 보존).

근거: document-archive 브랜치 archive/research/2026-07-11-playlist-sequencing-strategy.md §5.

실행
----
    python src/scripts/data/build_energy_full.py            # 분석·검증만(파일 미변경)
    python src/scripts/data/build_energy_full.py --write    # songs_master.csv 병합까지
"""

from __future__ import annotations

import argparse
import bisect
import csv
import sys
from pathlib import Path

import numpy as np

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
_MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
_FEATURES_CSV = _REPO_ROOT / "data" / "full_audio_features.csv"

# ---------------------------------------------------------------------------
# 그라운드트루스 (곡 정체성 기준. idx = songs_master.csv)
#   - QUIET   : 명백히 조용한 발라드/젠틀 (강도 낮아야 함)
#   - LOUD    : 명백히 시끄러운 락/파티 앤섬 (강도 높아야 함)
#   - MISJUDGED: 발췌 편향으로 프록시가 '조용'으로 오판한 실제 시끄러운 곡
#                (energy_full이 반드시 조용 그룹 위로 끌어올려야 하는 핵심 검증 대상)
# 라벨은 곡 정체성 기반의 방향성 근거(소규모·수작업). 통계적 유의성 주장 아님.
# ---------------------------------------------------------------------------
GT_QUIET = {
    272: "栞(mygo)", 281: "過惰幻(mygo)", 31: "青い栞(afterglow)",
    343: "ホワイトノスタルジア(pastel)", 213: "胡蝶翔る星月夜(morfonica)",
    387: "八月のif(popipa)", 131: "ひまわりの約束(hhw)",
    412: "1000回潤んだ空(popipa)", 603: "鳥の詩(roselia)", 589: "約束(roselia)",
    261: "壱雫空(mygo)", 456: "遠い音楽~ハートビート~(popipa)",
    191: "誓いのWingbeat(morfonica)", 269: "迷路日々(mygo)",
}
GT_LOUD = {
    584: "FIRE BIRD(roselia)", 501: "R・I・O・T(RAS)", 500: "EXPOSE(RAS)",
    578: "Determination Symphony(roselia)", 614: "PASSIONATE ANTHEM(roselia)",
    506: "Sacred world(RAS)", 591: "Song I am.(roselia)", 386: "Time Lapse(popipa)",
    10: "Y.O.L.O!!!!!(afterglow)", 490: "Invincible Fighter(RAS)",
    491: "A DECLARATION OF×××(RAS)", 494: "HELL! or HELL?(RAS)",
    583: "BRAVE JEWEL(roselia)", 574: "ONENESS(roselia)",
}
# 티켓 핵심 성공기준 4곡(★) + 보고된 누출곡
GT_MISJUDGED = {
    278: "★処救生(mygo)", 512: "★灼熱 Bonfire!(RAS)",
    336: "★ドラマチック！アライブ(pastel)", 155: "★はいよろこんで(hhw)",
    366: "惑星ループ(pastel)", 181: "メランコリックララバイ(morfonica)",
    79: "黒のバースデイ(ave_mujica)", 486: "ヴァンパイア(popipa)",
}
STRICT4 = [278, 512, 336, 155]  # 반드시 栞·過惰幻 위로

# composite 후보에 쓰는 서브피처(오리엔테이션 = '클수록 시끄러움' 기준 부호).
# 부호는 그라운드트루스로 자동 결정하되, 아래는 사전 기대 방향(문서화용):
#   perc(+), zcr(+), flat(+), cen(+), roll(+), bw(+), onset(+), onset_rate(+),
#   contrast(-)  ← 시끄러운 왜곡음일수록 스펙트럼 대비가 낮아짐(잡음바닥↑)
CANDIDATE_FEATS = [
    "perc_mean", "perc_p90", "perc_p95",
    "onset_mean", "onset_p90", "onset_rate",
    "zcr_mean", "zcr_p90",
    "cen_mean", "cen_p90",
    "roll_mean", "roll_p90",
    "bw_mean", "bw_p90",
    "flat_mean", "flat_p90",
    "contrast_mean", "contrast_p90",
    "rms_mean", "rms_p90",  # 피크 라우드니스(FIRE BIRD 등 다이나믹 곡 구제용)
]


def _load_merged() -> list[dict]:
    master = {int(r["idx"]): r for r in csv.DictReader(
        _MASTER_CSV.open(encoding="utf-8", newline=""))}
    feats = {}
    for r in csv.DictReader(_FEATURES_CSV.open(encoding="utf-8", newline="")):
        if (r.get("cen_mean") or "").strip() and not (r.get("error") or "").strip():
            feats[int(r["idx"])] = r  # 마지막(최신) 행 우선 → resume/재추출 안전
    merged = []
    for idx, m in master.items():
        if idx in feats:
            row = dict(m)
            for c in CANDIDATE_FEATS + ["duration_sec"]:
                row[c] = float(feats[idx][c])
            row["_idx"] = idx
            row["_elig"] = str(m["eligible_band"]).strip().lower() == "true"
            merged.append(row)
    return merged


def _zscores(rows: list[dict], feat: str, pool_mask: list[bool]) -> dict[int, float]:
    """eligible 풀 기준 robust z-score(중앙값/MAD). 이상치에 강건."""
    vals = np.array([r[feat] for r, m in zip(rows, pool_mask) if m])
    med = np.median(vals)
    mad = np.median(np.abs(vals - med)) * 1.4826  # 정규분포 근사 스케일
    if mad < 1e-9:
        mad = vals.std() + 1e-9
    return {r["_idx"]: (r[feat] - med) / mad for r in rows}


def _auc(pos: list[float], neg: list[float]) -> float:
    """pos가 neg보다 크면 1에 가까움(Mann-Whitney U / n1n2)."""
    n1, n2 = len(pos), len(neg)
    if n1 == 0 or n2 == 0:
        return float("nan")
    allv = [(v, 1) for v in pos] + [(v, 0) for v in neg]
    allv.sort(key=lambda t: t[0])
    ranks = {}
    i = 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[k] = avg
        i = j
    r_pos = sum(ranks[k] for k, (_, lab) in enumerate(allv) if lab == 1)
    u = r_pos - n1 * (n1 + 1) / 2.0
    return u / (n1 * n2)


def _cohens_d(pos: list[float], neg: list[float]) -> float:
    pos, neg = np.array(pos), np.array(neg)
    nx, ny = len(pos), len(neg)
    sp = np.sqrt(((nx - 1) * pos.var(ddof=1) + (ny - 1) * neg.var(ddof=1)) / (nx + ny - 2))
    return float((pos.mean() - neg.mean()) / (sp + 1e-9))


def _percentile_ranker(values: list[float]):
    srt = sorted(values)
    n = len(srt)

    def rank(v: float) -> float:
        if n == 0:
            return 0.5
        less = bisect.bisect_left(srt, v)
        equal = bisect.bisect_right(srt, v) - less
        return (less + 0.5 * equal) / n

    return rank


def _current_intensity(rows: list[dict], pool_mask: list[bool]) -> dict[int, float]:
    """현재 엔진(song_repo)의 intensity 재현: percentile+power-mean(p=3)."""
    p = 3
    elig = [r for r, m in zip(rows, pool_mask) if m]
    re = _percentile_ranker([-float(r["energy_proxy"]) for r in elig])
    ra = _percentile_ranker([-float(r["acousticness_proxy"]) for r in elig])
    out = {}
    for r in rows:
        pe = re(-float(r["energy_proxy"]))
        pa = ra(-float(r["acousticness_proxy"]))
        out[r["_idx"]] = ((pe ** p + pa ** p) / 2.0) ** (1.0 / p)
    return out


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="songs_master.csv 병합 기록")
    args = ap.parse_args()

    rows = _load_merged()
    n_total = len(rows)
    pool_mask = [r["_elig"] for r in rows]
    n_elig = sum(pool_mask)
    print(f"병합된 곡: {n_total} (eligible {n_elig}) — 추출 완료분만.")
    gt_all = set(GT_QUIET) | set(GT_LOUD) | set(GT_MISJUDGED)
    have = {r["_idx"] for r in rows}
    missing_gt = sorted(gt_all - have)
    if missing_gt:
        print(f"[주의] 그라운드트루스 중 미추출 idx: {missing_gt}")

    # --- 오리엔테이션 정한 z-score (클수록 시끄러움) ---
    z: dict[str, dict[int, float]] = {}
    orient: dict[str, int] = {}
    q_idx = [i for i in GT_QUIET if i in have]
    l_idx = [i for i in GT_LOUD if i in have]
    for feat in CANDIDATE_FEATS:
        zf = _zscores(rows, feat, pool_mask)
        qm = np.mean([zf[i] for i in q_idx])
        lm = np.mean([zf[i] for i in l_idx])
        s = 1 if lm >= qm else -1
        orient[feat] = s
        z[feat] = {i: s * v for i, v in zf.items()}

    def feat_vals(feat, idxs):
        return [z[feat][i] for i in idxs]

    print("\n=== 단일 피처 분리력 (QUIET vs LOUD, oriented) ===")
    print(f"{'feat':<15}{'AUC':>7}{'d':>7}{'orient':>7}")
    singles = []
    for feat in CANDIDATE_FEATS:
        auc = _auc(feat_vals(feat, l_idx), feat_vals(feat, q_idx))
        d = _cohens_d(feat_vals(feat, l_idx), feat_vals(feat, q_idx))
        singles.append((feat, auc, d))
        print(f"{feat:<15}{auc:>7.3f}{d:>7.2f}{orient[feat]:>7d}")

    # --- composite 후보들 ---
    def comp(idx, feats, weights=None):
        if weights is None:
            weights = [1.0] * len(feats)
        return sum(w * z[f][idx] for f, w in zip(feats, weights)) / sum(weights)

    # === 최종 복합 (부장 확정 2026-07-11) ===
    # 데이터팀 자동선정 mean-5feat은 AUC 0.954지만 FIRE BIRD(다이나믹 빌드업)를 pct 0.09로
    # 오판(조용 처리) → 실패. 부장 재분석: mean-5feat + rms_p90(피크 라우드니스, 가중 ×2)을
    # 더하면 FIRE BIRD를 0.82로 구제하면서 misjudged party곡(灼熱·ドラマ·はいよろ)을 조용
    # 그룹 위로 유지(AUC 0.990). (処救生은 전 오디오 피처에서 subdued로 측정되는 잔여 한계 —
    # 보고서에 문서화.)
    FINAL_FEATS = ["perc_mean", "onset_mean", "zcr_mean", "cen_mean", "flat_mean", "rms_p90"]
    FINAL_W = [1, 1, 1, 1, 1, 2]
    recipes = {
        "mean-5feat(데이터팀 자동선정 — FIRE BIRD 실패)":
            (["perc_mean", "onset_mean", "zcr_mean", "cen_mean", "flat_mean"], None),
        "FINAL(mean5+rms_p90x2, 부장 확정)": (FINAL_FEATS, FINAL_W),
    }

    cur = _current_intensity(rows, pool_mask)
    elig_rows = [r for r in rows if r["_elig"]]

    def pct_ranks(score_map):
        rk = _percentile_ranker([score_map[r["_idx"]] for r in elig_rows])
        return {r["_idx"]: rk(score_map[r["_idx"]]) for r in rows}

    cur_pct = pct_ranks(cur)
    print("\n[기준선] 현재 intensity (percentile+power-mean p=3):")
    print(f"  QUIET-vs-LOUD AUC={_auc([cur[i] for i in l_idx], [cur[i] for i in q_idx]):.3f}")
    for i in STRICT4:
        if i in have:
            print(f"  {GT_MISJUDGED[i]:<28} pct={cur_pct[i]:.3f}")

    print("\n=== composite 후보 비교 (AUC QUIET-vs-LOUD) ===")
    for _nm, (_fs, _w) in recipes.items():
        _s = {r["_idx"]: comp(r["_idx"], _fs, _w) for r in rows}
        print(f"  {_nm:<44} AUC={_auc([_s[i] for i in l_idx], [_s[i] for i in q_idx]):.3f}")

    # --- 최종 composite → energy_full ---
    feats, w = FINAL_FEATS, FINAL_W
    sc = {r["_idx"]: comp(r["_idx"], feats, w) for r in rows}
    auc = _auc([sc[i] for i in l_idx], [sc[i] for i in q_idx])
    pr = pct_ranks(sc)
    margin = (min(pr[i] for i in STRICT4 if i in have)
              - max(pr[i] for i in (272, 281) if i in have))
    name = "FINAL(mean5+rms_p90x2)"
    print(f"\n=== 최종 energy_full = percentile_rank(composite) over eligible ===")
    print(f"composite = mean of oriented z: {list(zip(feats, (w or [1]*len(feats))))}")
    print(f"QUIET-vs-LOUD AUC={auc:.3f}  strict4 margin={margin:+.3f}")

    print("\n--- 문제곡 재순위 (energy_full ∈ [0,1], 클수록 시끄러움) ---")
    print(f"{'song':<30}{'현재int_pct':>12}{'energy_full':>12}{'Δ':>8}")
    for label, group in (("MISJUDGED", GT_MISJUDGED), ("QUIET-anchor", {272: GT_QUIET[272], 281: GT_QUIET[281], 31: GT_QUIET[31]}),
                         ("LOUD-anchor", {584: GT_LOUD[584], 501: GT_LOUD[501], 500: GT_LOUD[500]})):
        print(f"[{label}]")
        for i, nm in group.items():
            if i in have:
                print(f"  {nm:<28}{cur_pct[i]:>12.3f}{pr[i]:>12.3f}{pr[i]-cur_pct[i]:>+8.3f}")

    # 분리도(조용GT vs 시끄러움GT의 평균 energy_full 차)
    q_ef = np.mean([pr[i] for i in q_idx])
    l_ef = np.mean([pr[i] for i in l_idx])
    m_ef = np.mean([pr[i] for i in GT_MISJUDGED if i in have])
    print(f"\n분리도(energy_full): QUIET평균={q_ef:.3f}  MISJUDGED평균={m_ef:.3f}  "
          f"LOUD평균={l_ef:.3f}  (LOUD-QUIET={l_ef-q_ef:.3f})")
    q_cur = np.mean([cur_pct[i] for i in q_idx])
    l_cur = np.mean([cur_pct[i] for i in l_idx])
    m_cur = np.mean([cur_pct[i] for i in GT_MISJUDGED if i in have])
    print(f"분리도(현재int) : QUIET평균={q_cur:.3f}  MISJUDGED평균={m_cur:.3f}  "
          f"LOUD평균={l_cur:.3f}  (LOUD-QUIET={l_cur-q_cur:.3f})")

    if not args.write:
        print("\n(--write 미지정: songs_master.csv 미변경. 분석만 수행.)")
        return

    # --- songs_master.csv 병합: energy_full 컬럼 추가(기존 보존) ---
    _write_master(pr, feats, w)


def _write_master(pr: dict[int, float], feats, w) -> None:
    with _MASTER_CSV.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames)
        master_rows = list(reader)
    new_cols = [c for c in ["energy_full"] if c not in cols]
    out_cols = cols + new_cols
    n_filled = 0
    for r in master_rows:
        idx = int(r["idx"])
        if idx in pr:
            r["energy_full"] = f"{pr[idx]:.6f}"
            n_filled += 1
        else:
            r["energy_full"] = ""  # 미추출 곡은 공란(코드팀이 결측 처리)
    with _MASTER_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_cols)
        writer.writeheader()
        writer.writerows(master_rows)
    print(f"\n[WRITE] songs_master.csv 병합 완료: energy_full 채워진 행={n_filled}/{len(master_rows)}")
    print(f"        composite feats={feats} weights={w}")


if __name__ == "__main__":
    main()
