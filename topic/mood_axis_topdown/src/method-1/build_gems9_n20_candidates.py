"""GEMS-9 n>=20 확대 라운드 곡 선정 — 밴드×PC1삼분위 균형표집 + 동시 홀드아웃 추첨.

통계 자문(report/04-n20_sampling_consult.md) 결과를 그대로 구현한다. 요약:
- 모집단: eligible_band==True 중 15곡 미만 밴드 및 various_artists 제외 (10개 밴드).
- 추정대상: 카탈로그 전체(모집단) 대상 주변부(marginal) 상관 — within/between 어느 한쪽이
  아니라 "이 카탈로그에서 필터로 쓸 만한가"가 목적이므로, 밴드 크기 비례 배분(+최소하한)을
  쓴다.
- 균형표집: 예전 energy_full 극단추출(범위왜곡)과 달리, 전체 모집단에서 뽑은 대표축(PC1)의
  분포를 각 밴드 내부에서 삼분위로 층화한 뒤 그 안에서 무작위 추출 — 표본의 피쳐 분포가
  모집단을 따라가게 해서 범위왜곡 없이 정밀도만 올린다.
- 피쳐 차원축소는 표본이 아니라 이 스크립트가 다루는 모집단 전체에서 수행해 누수를 막는다
  (상관 클러스터링 → 클러스터별 대표 피쳐 1개, 필터 스크리닝 때 이 대표 피쳐만 검정).
- 홀드아웃(확증용) 20~30곡은 본표본과 "같은 시드 절차에서 연속으로" 뽑아 disjoint 확보 —
  1차 분석 결과를 보고 나중에 뽑지 않는다(사전등록 원칙, notes/n20_prereg.md).
- 포함확률(inclusion probability)을 셀 단위로 기록해 분석 단계의 사후층화 가중치 계산에 쓴다.

재현성: RNG 시드는 아래 SEED 상수 하나로 고정. 한 번 뽑은 뒤 결과가 마음에 안 든다고
재실행하지 않는다 — 재실행이 필요한 유일한 사유는 assign_rater_blocks.py 쪽의 "연결성/
곡당 최소 응답자 수 미달" 같은 사전에 정한 객관적 기준뿐(이 스크립트 자체의 산출물과는
무관).
"""
import csv
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[4]
AUDIO_FEATS_PATH = ROOT / "topic" / "audio_feats_analysis" / "out" / "audio_feats.csv"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "out"

SEED = 20260723  # 고정 시드 — 사전등록 이후 변경 금지

MIN_SONGS_PER_BAND = 15
EXCLUDED_BANDS = {"various_artists"}

TIER1 = [
    "mfcc_1_mean", "mfcc_2_mean", "mfcc_3_mean", "mfcc_4_mean", "mfcc_5_mean",
    "mfcc_6_mean", "mfcc_7_mean", "mfcc_8_mean", "mfcc_9_mean", "mfcc_10_mean",
    "mfcc_11_mean", "mfcc_12_mean", "mfcc_13_mean",
    "contrast_mean", "energy_full", "rms_mean", "bpm",
]
TIER2 = ["mode_score", "tempo_bpm"]
FEATURE_COLS = TIER1 + TIER2

MAIN_TOTAL_TARGET = 70
MAIN_FLOOR_PER_BAND = 4
HOLDOUT_TOTAL_TARGET = 25
HOLDOUT_FLOOR_PER_BAND = 2

CLUSTER_DISTANCE_THRESHOLD = 0.3  # 1-|rho| 기준. |rho|>0.7인 피쳐끼리 같은 클러스터.


def load_population():
    df = pd.read_csv(AUDIO_FEATS_PATH, encoding="utf-8")
    df = df[(df["eligible_band"] == True) | (df["eligible_band"] == "True")]
    df = df.dropna(subset=FEATURE_COLS + ["energy_full"])

    band_counts = df["band"].value_counts()
    keep_bands = [
        b for b, n in band_counts.items()
        if n >= MIN_SONGS_PER_BAND and b not in EXCLUDED_BANDS
    ]
    df = df[df["band"].isin(keep_bands)].reset_index(drop=True)
    return df, sorted(keep_bands)


def reduce_features(df):
    """전체 모집단에서 피쳐 상관 클러스터링 -> 클러스터별 대표 피쳐 1개."""
    X = df[FEATURE_COLS].to_numpy(dtype=float)
    corr = pd.DataFrame(X, columns=FEATURE_COLS).corr(method="spearman").to_numpy()
    dist = 1 - np.abs(corr)
    np.fill_diagonal(dist, 0.0)
    dist = (dist + dist.T) / 2  # 수치 오차로 인한 비대칭 제거
    condensed = squareform(dist, checks=False)
    Z = linkage(condensed, method="average")
    cluster_ids = fcluster(Z, t=CLUSTER_DISTANCE_THRESHOLD, criterion="distance")

    reps = []
    for cid in sorted(set(cluster_ids)):
        members = [f for f, c in zip(FEATURE_COLS, cluster_ids) if c == cid]
        if len(members) == 1:
            reps.append(members[0])
            continue
        # medoid: 클러스터 내 다른 멤버들과의 평균 |rho|가 가장 높은 피쳐
        idxs = [FEATURE_COLS.index(m) for m in members]
        sub = np.abs(corr[np.ix_(idxs, idxs)])
        avg_corr = (sub.sum(axis=1) - 1) / (len(idxs) - 1)
        reps.append(members[int(np.argmax(avg_corr))])

    return reps, dict(zip(FEATURE_COLS, cluster_ids))


def compute_pc1(df):
    X = df[FEATURE_COLS].to_numpy(dtype=float)
    Xs = StandardScaler().fit_transform(X)
    pca = PCA(n_components=1, random_state=SEED)
    pc1 = pca.fit_transform(Xs).ravel()
    return pc1, float(pca.explained_variance_ratio_[0])


def band_tertiles(df):
    """밴드 내부에서 PC1 삼분위 라벨(0/1/2) 부여."""
    df = df.copy()
    df["pc1_tertile"] = (
        df.groupby("band")["pc1"]
        .transform(lambda s: pd.qcut(s, 3, labels=False, duplicates="drop"))
    )
    df["pc1_tertile"] = df["pc1_tertile"].fillna(1).astype(int)  # 곡 부족으로 못 나뉜 경우 중간 취급
    return df


def largest_remainder_allocation(sizes, total, floor):
    """band_size 비례 + floor 적용, largest remainder로 정수화해 total에 정확히 맞춤."""
    bands = list(sizes.keys())
    pop = np.array([sizes[b] for b in bands], dtype=float)
    raw = pop / pop.sum() * total
    raw = np.maximum(raw, floor)
    # floor 적용으로 초과분 발생 시 비례 축소 후 다시 floor 보정(반복)
    for _ in range(20):
        excess = raw.sum() - total
        if abs(excess) < 1e-9:
            break
        above_floor = raw > floor + 1e-9
        if excess > 0 and above_floor.any():
            raw[above_floor] -= excess * (raw[above_floor] / raw[above_floor].sum())
            raw = np.maximum(raw, floor)
        else:
            break
    base = np.floor(raw).astype(int)
    remainder = total - base.sum()
    frac_order = np.argsort(-(raw - base))
    for i in range(remainder):
        base[frac_order[i % len(base)]] += 1
    return dict(zip(bands, base.tolist()))


def allocate_within_band_tertiles(band_df, n_band, rng):
    """밴드 내 N을 3개 삼분위 셀 크기 비례로 배분(largest remainder)."""
    cell_sizes = band_df["pc1_tertile"].value_counts().to_dict()
    for t in (0, 1, 2):
        cell_sizes.setdefault(t, 0)
    tertiles = sorted(cell_sizes)
    sizes = np.array([cell_sizes[t] for t in tertiles], dtype=float)
    if sizes.sum() == 0:
        return {t: 0 for t in tertiles}
    raw = sizes / sizes.sum() * n_band
    raw = np.minimum(raw, sizes)  # 셀 크기 초과 배분 방지
    base = np.floor(raw).astype(int)
    remainder = n_band - base.sum()
    frac_order = list(np.argsort(-(raw - base)))
    i = 0
    guard = 0
    while remainder > 0 and guard < 1000:
        j = frac_order[i % len(frac_order)]
        if base[j] < sizes[j]:
            base[j] += 1
            remainder -= 1
        i += 1
        guard += 1
    return dict(zip(tertiles, base.tolist()))


def draw_sample(pool_df, band_alloc, rng):
    """band_alloc(밴드->N)을 밴드×삼분위 셀 배분으로 세분화해 무작위 추출.

    반환: (뽑힌 행들의 DataFrame(inclusion_prob 포함), 남은 pool_df)
    """
    picked_idx = []
    weight_rows = []
    for band, n_band in band_alloc.items():
        if n_band <= 0:
            continue
        band_df = pool_df[pool_df["band"] == band]
        cell_alloc = allocate_within_band_tertiles(band_df, n_band, rng)
        for tertile, n_cell in cell_alloc.items():
            if n_cell <= 0:
                continue
            cell_df = band_df[band_df["pc1_tertile"] == tertile]
            chosen = rng.choice(cell_df.index.to_numpy(), size=n_cell, replace=False)
            incl_prob = n_cell / len(cell_df)
            picked_idx.extend(chosen.tolist())
            for idx in chosen:
                weight_rows.append({"idx_row": idx, "inclusion_prob": incl_prob})

    picked = pool_df.loc[picked_idx].copy()
    weights = pd.DataFrame(weight_rows).set_index("idx_row")
    picked["inclusion_prob"] = weights["inclusion_prob"]
    remaining = pool_df.drop(index=picked_idx)
    return picked, remaining


def main():
    df, bands = load_population()
    print(f"모집단: {len(df)}곡, {len(bands)}개 밴드 -> {bands}")

    rep_features, cluster_map = reduce_features(df)
    print(f"\n대표 피쳐(클러스터당 1개, 총 {len(rep_features)}개): {rep_features}")

    pc1, explained = compute_pc1(df)
    df = df.assign(pc1=pc1)
    print(f"PC1 설명분산비: {explained:.3f}")

    df = band_tertiles(df)

    rng = np.random.default_rng(SEED)  # 본표본 + 홀드아웃을 하나의 시드 절차로 연속 추첨

    band_sizes = df["band"].value_counts().to_dict()
    main_alloc = largest_remainder_allocation(band_sizes, MAIN_TOTAL_TARGET, MAIN_FLOOR_PER_BAND)
    print(f"\n본표본 밴드별 배분(목표 {MAIN_TOTAL_TARGET}): {main_alloc}")

    main_sample, remaining = draw_sample(df, main_alloc, rng)
    print(f"본표본 실제 추출: {len(main_sample)}곡")

    remaining_sizes = remaining["band"].value_counts().to_dict()
    holdout_alloc = largest_remainder_allocation(
        remaining_sizes, HOLDOUT_TOTAL_TARGET, HOLDOUT_FLOOR_PER_BAND
    )
    print(f"홀드아웃 밴드별 배분(목표 {HOLDOUT_TOTAL_TARGET}): {holdout_alloc}")

    holdout_sample, _ = draw_sample(remaining, holdout_alloc, rng)
    print(f"홀드아웃 실제 추출: {len(holdout_sample)}곡 (본표본과 disjoint 보장됨)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["idx", "band", "song", "url", "video_id", "pc1", "pc1_tertile", "inclusion_prob"]

    main_out = main_sample[cols].sort_values(["band", "pc1"])
    main_out.to_csv(OUT_DIR / "gems9_n20_candidates.csv", index=False, encoding="utf-8-sig")
    print(f"\n-> {OUT_DIR / 'gems9_n20_candidates.csv'} ({len(main_out)}행)")

    holdout_out = holdout_sample[cols].sort_values(["band", "pc1"])
    holdout_out.to_csv(OUT_DIR / "gems9_n20_holdout_sealed.csv", index=False, encoding="utf-8-sig")
    print(f"-> {OUT_DIR / 'gems9_n20_holdout_sealed.csv'} ({len(holdout_out)}행) "
          f"[봉인: 본표본 1차 분석 끝나기 전엔 채점/열람 금지]")

    with open(OUT_DIR / "gems9_n20_representative_features.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["feature", "cluster_id", "is_representative"])
        for feat in FEATURE_COLS:
            w.writerow([feat, cluster_map[feat], feat in rep_features])
    print(f"-> {OUT_DIR / 'gems9_n20_representative_features.csv'}")

    overlap = set(main_out["idx"]) & set(holdout_out["idx"])
    assert not overlap, f"본표본/홀드아웃 중복 발생: {overlap}"
    print("\n중복 검증 통과: 본표본 ∩ 홀드아웃 = 공집합")


if __name__ == "__main__":
    main()
