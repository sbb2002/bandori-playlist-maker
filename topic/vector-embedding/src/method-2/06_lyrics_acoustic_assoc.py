"""부속 연구: 가사 감성 ↔ 음향 특성 연관 분석 (DESIGN.md §9, n=661).

사람 청취가 필요 없는 관찰 연구 -- §1~§5와 독립적으로 돌아간다. 설문 대기 중 완료 가능.

분석 구성:
  A1 (§9b): desc 임베딩을 앵커 차이벡터에 투영한 감성 축(lyr_valence/lyr_arousal) ×
            음향 변수 Spearman(주)/Pearson(부) 상관
  A2 (§9c): category1∪category2 중 n>=20 키워드 그룹 vs 나머지 Cohen's d + Mann-Whitney U
  A3 (§9d): desc 임베딩 -> 음향 변수 Ridge 회귀의 out-of-fold R² (KFold / GroupKFold 양쪽)
  A4 (§9f): 곡별 불일치 지표 사전 계산 (설문 완료 후 사람 점수와 대조 -- 지금은 저장만)

§9e 게이트: FDR(BH, q<0.05) **그리고** 효과크기 하한(|rho|>=0.2 / |d|>=0.3)을 둘 다 통과해야
`passes_threshold=True`. n=661에서는 |rho|~0.11이면 이미 p<0.005라 유의성만으로는 무의미하다.

음성 대조군(§9a): `energy`·`energy_proxy`는 §1a에서 무효/역전으로 판명된 컬럼이다. 일부러
포함하며, 이들이 §9e 기준을 통과하면 **파이프라인 오류 신호**다.

Outputs (§9g):
  - out/lyrics_emotion_axes.csv
  - out/assoc_correlations.csv
  - out/assoc_category_contrast.csv
  - out/assoc_ceiling.csv
  - out/lyrics_acoustic_alignment.csv
  - out/assoc_anchor_loo.csv          (§9h 앵커 LOO 민감도)
  - fig/assoc_heatmap.png
"""
import bisect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
FIG_DIR = SCRIPT_DIR / "fig"
PROGRESS_PATH = config.OUT_DIR / "assoc_progress.json"

# ============================================================================
# §9e 사전 선언 상수 -- 결과를 본 뒤에 바꾸는 것은 금지
# ============================================================================
RHO_MIN = 0.2      # A1 효과크기 하한 (분산의 약 4%)
D_MIN = 0.3        # A2 효과크기 하한
Q_MAX = 0.05       # FDR(BH) 임계
KEYWORD_MIN_N = 20  # A2 키워드 그룹 최소 출현 수
ANCHOR_LOO_MIN = 0.9  # §9h: LOO 변형 간 상관이 이 값 미만이면 축을 신뢰하지 말 것

# §9b 앵커 -- 연구자 직관이며 사전 검증되지 않았다(§9h). LOO 민감도로 확인한다.
EMOTION_AXES = {
    "lyr_valence": {
        "positive": ["행복", "기쁨", "희망", "설렘", "사랑"],
        "negative": ["슬픔", "절망", "우울", "고독", "상실"],
    },
    "lyr_arousal": {
        "positive": ["열정", "흥분", "질주", "격렬", "환호"],
        "negative": ["평온", "차분", "잔잔", "고요", "나른함"],
    },
}

# §9a 음향 변수 -- 역할별로 구분한다(리포트에서 검증됨/탐색적/대조군을 나눠 읽기 위함).
FEATURES_VERIFIED = [
    "intensity", "energy_full",
    "i_mean", "i_std", "i_min", "i_max", "i_start", "i_end",
    "mode_score", "bpm",
]
FEATURES_EXPLORATORY = ["acousticness_proxy", "instrumentalness_proxy"]
FEATURES_LIBROSA = [
    "cen_mean", "cen_p90", "roll_mean", "roll_p90", "bw_mean", "bw_p90",
    "flat_mean", "flat_p90", "contrast_mean", "contrast_p90",
    "zcr_mean", "zcr_p90", "perc_mean", "perc_p90", "perc_p95",
    "onset_mean", "onset_p90", "onset_rate", "rms_mean", "rms_p90",
]
# §9a 음성 대조군: 통과하면 파이프라인 오류 신호.
FEATURES_NEGATIVE_CONTROL = ["energy", "energy_proxy"]

FEATURE_ROLE = {}
for _f in FEATURES_VERIFIED:
    FEATURE_ROLE[_f] = "verified"
for _f in FEATURES_EXPLORATORY:
    FEATURE_ROLE[_f] = "exploratory"
for _f in FEATURES_LIBROSA:
    FEATURE_ROLE[_f] = "librosa_direct"
for _f in FEATURES_NEGATIVE_CONTROL:
    FEATURE_ROLE[_f] = "negative_control"

ALL_FEATURES = (
    FEATURES_VERIFIED + FEATURES_EXPLORATORY + FEATURES_LIBROSA + FEATURES_NEGATIVE_CONTROL
)

# A2 §9c의 명시적 대비: "슬픔·절망·우울" 계열 vs "행복·기쁨" 계열.
# 키워드는 LLM 자유 생성이라 어휘가 갈리므로 계열을 부분문자열 집합으로 정의한다.
SAD_FAMILY = ["슬픔", "슬픈", "절망", "우울", "고독", "상실", "비애", "쓸쓸", "외로", "허무", "체념"]
HAPPY_FAMILY = ["행복", "기쁨", "기쁜", "즐거", "환희", "유쾌", "쾌활", "명랑"]


def save_progress(progress, **fields):
    progress.update(fields)
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def percentile_ranker(values):
    """song_repo._percentile_ranker와 동일한 백분위 함수. rank(v) ∈ [0,1]."""
    srt = sorted(values)
    n = len(srt)

    def rank(v):
        if n == 0:
            return 0.5
        less = bisect.bisect_left(srt, v)
        equal = bisect.bisect_right(srt, v) - less
        return (less + 0.5 * equal) / n

    return rank


def bh_fdr(pvals):
    """Benjamini-Hochberg FDR 보정. p값 배열 -> q값 배열(입력 순서 유지).

    topic/mood_warmth 1라운드의 관례를 승계(§9e).
    """
    p = np.asarray(pvals, dtype=float)
    n = len(p)
    if n == 0:
        return np.array([])
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * n / (np.arange(n) + 1)
    # 단조성 보장: 뒤에서부터 누적 최솟값
    q = np.minimum.accumulate(q[::-1])[::-1]
    q = np.clip(q, 0, 1)
    out = np.empty(n, dtype=float)
    out[order] = q
    return out


def cohens_d(a, b):
    """Cohen's d (pooled SD)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return np.nan
    va, vb = a.var(ddof=1), b.var(ddof=1)
    pooled = ((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)
    if pooled <= 0:
        return np.nan
    return (a.mean() - b.mean()) / np.sqrt(pooled)


# ============================================================================
# 데이터 적재 (§9a)
# ============================================================================
def load_data():
    """가사 프로필 + 음향 변수를 tag/idx 기준으로 결합한다.

    full_audio_features.csv는 663행, songs_master.csv는 661행이다(중복 업로드 2곡 제거
    이력, 커밋 ead15e3). idx 기준 inner join으로 661행에 맞추고 탈락 행 수를 로그로 남긴다.
    """
    print("=== §9a 데이터 적재 ===")

    df_profiles = pd.read_csv(config.METHOD_1_OUT_DIR / "song_profiles.csv")
    print(f"  song_profiles.csv: {len(df_profiles)}행")

    df_acoustics = pd.read_csv(config.OUT_DIR / "song_acoustics.csv")
    print(f"  song_acoustics.csv: {len(df_acoustics)}행")

    df_master = pd.read_csv(config.SONGS_MASTER_CSV)
    print(f"  songs_master.csv: {len(df_master)}행")

    full_feat_path = config.SONGS_MASTER_CSV.parent / "full_audio_features.csv"
    df_full = pd.read_csv(full_feat_path)
    print(f"  full_audio_features.csv: {len(df_full)}행")

    # §9a: idx 기준 inner join으로 661에 맞춘다.
    n_full_before = len(df_full)
    df_full_j = df_full.drop(columns=[c for c in ("band", "song", "duration_sec") if c in df_full.columns])
    dropped_idx = sorted(set(df_full["idx"]) - set(df_master["idx"]))
    print(f"  [inner join] full_audio_features에서 탈락한 행: {n_full_before - len(df_master)}건 "
          f"(idx={dropped_idx})")

    # songs_master 쪽 음향 원값
    master_cols = ["idx"] + [
        c for c in (FEATURES_VERIFIED + FEATURES_EXPLORATORY + FEATURES_NEGATIVE_CONTROL)
        if c in df_master.columns
    ]
    df = df_acoustics.merge(df_master[master_cols], on="idx", how="inner")
    print(f"  song_acoustics × songs_master inner join: {len(df)}행")

    df = df.merge(df_full_j, on="idx", how="inner")
    print(f"  × full_audio_features inner join: {len(df)}행")

    df = df.merge(df_profiles[["tag", "desc", "category1", "category2"]], on="tag", how="inner")
    print(f"  × song_profiles inner join: {len(df)}행")

    # error 컬럼(librosa 추출 실패 표시)이 있으면 확인만 하고 남긴다.
    if "error" in df.columns:
        n_err = df["error"].notna().sum()
        if n_err:
            print(f"  WARNING: full_audio_features error 컬럼 비어있지 않은 행 {n_err}건")

    missing = [f for f in ALL_FEATURES if f not in df.columns]
    if missing:
        print(f"  WARNING: 요청된 음향 변수 중 누락: {missing}")

    print(f"  최종 분석 데이터: {len(df)}행\n")
    return df


# ============================================================================
# A1 (§9b): 감성 축 투영
# ============================================================================
def build_emotion_axes(df, model):
    """desc 임베딩을 앵커 차이벡터에 투영해 해석 가능한 스칼라를 만든다.

    axis_vec = mean(emb(positive)) - mean(emb(negative))
    score(곡) = cosine(emb(desc), axis_vec)

    차이 벡터를 쓰는 이유(§9b): Phase 1에서 bge-m3 raw cosine이 0.658~0.720으로 극도로
    압축돼 있었다. 차이 벡터는 공통 성분을 상쇄하므로 이 압축 문제를 회피한다.
    """
    print("=== §9b A1: 감성 축 투영 ===")

    print(f"  desc {len(df)}건 임베딩 중...")
    desc_vecs = model.encode(
        df["desc"].tolist(), normalize_embeddings=True, show_progress_bar=False
    )

    axes_scores = {}
    for axis_name, anchors in EMOTION_AXES.items():
        pos_vecs = model.encode(anchors["positive"], normalize_embeddings=True, show_progress_bar=False)
        neg_vecs = model.encode(anchors["negative"], normalize_embeddings=True, show_progress_bar=False)
        axis_vec = pos_vecs.mean(axis=0) - neg_vecs.mean(axis=0)
        axis_vec = axis_vec / np.linalg.norm(axis_vec)
        scores = desc_vecs @ axis_vec  # desc는 이미 normalize됨 -> cosine
        axes_scores[axis_name] = scores
        print(f"  {axis_name}: min={scores.min():.4f}, max={scores.max():.4f}, "
              f"mean={scores.mean():.4f}, sd={scores.std():.4f}")

    return desc_vecs, axes_scores


def anchor_loo_sensitivity(df, model, desc_vecs):
    """§9h 앵커 LOO 민감도: 앵커를 하나씩 빼며 만든 축 변형들 간 상관.

    상관이 0.9 미만이면 축을 신뢰하지 말 것(§9h).
    """
    print("\n=== §9h 앵커 LOO 민감도 검사 ===")
    rows = []

    for axis_name, anchors in EMOTION_AXES.items():
        all_anchors = [("positive", w) for w in anchors["positive"]] + \
                      [("negative", w) for w in anchors["negative"]]

        # 전체 앵커 축(기준)
        pos_full = model.encode(anchors["positive"], normalize_embeddings=True, show_progress_bar=False)
        neg_full = model.encode(anchors["negative"], normalize_embeddings=True, show_progress_bar=False)
        v_full = pos_full.mean(axis=0) - neg_full.mean(axis=0)
        v_full = v_full / np.linalg.norm(v_full)
        s_full = desc_vecs @ v_full

        variants = {}
        for side, word in all_anchors:
            pos_w = [w for w in anchors["positive"] if not (side == "positive" and w == word)]
            neg_w = [w for w in anchors["negative"] if not (side == "negative" and w == word)]
            pv = model.encode(pos_w, normalize_embeddings=True, show_progress_bar=False)
            nv = model.encode(neg_w, normalize_embeddings=True, show_progress_bar=False)
            v = pv.mean(axis=0) - nv.mean(axis=0)
            v = v / np.linalg.norm(v)
            variants[f"-{word}"] = desc_vecs @ v

        # 변형 간 pairwise Pearson 상관(§9h: "LOO 변형 간 상관")
        names = list(variants.keys())
        pairwise = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                r = stats.pearsonr(variants[names[i]], variants[names[j]])[0]
                pairwise.append(r)
        pairwise = np.array(pairwise)

        # 각 변형 vs 전체 앵커 축 상관(부가 정보)
        vs_full = np.array([stats.pearsonr(variants[n], s_full)[0] for n in names])

        min_pair = float(pairwise.min())
        stable = min_pair >= ANCHOR_LOO_MIN

        print(f"  {axis_name}: LOO 변형 {len(names)}개")
        print(f"    변형 간 pairwise 상관: min={min_pair:.4f}, mean={pairwise.mean():.4f}, "
              f"max={pairwise.max():.4f}")
        print(f"    변형 vs 전체축 상관: min={vs_full.min():.4f}, mean={vs_full.mean():.4f}")
        if not stable:
            print(f"    *** WARNING: 변형 간 최소 상관 {min_pair:.4f} < {ANCHOR_LOO_MIN} "
                  f"-- §9h에 따라 이 축을 신뢰하지 말 것 ***")
        else:
            print(f"    (ok) 최소 상관 >= {ANCHOR_LOO_MIN} -- 축 안정")

        rows.append({
            "axis": axis_name,
            "n_variants": len(names),
            "pairwise_min": round(min_pair, 4),
            "pairwise_mean": round(float(pairwise.mean()), 4),
            "pairwise_max": round(float(pairwise.max()), 4),
            "vs_full_min": round(float(vs_full.min()), 4),
            "vs_full_mean": round(float(vs_full.mean()), 4),
            "stable": stable,
        })

    df_loo = pd.DataFrame(rows)
    loo_csv = config.OUT_DIR / "assoc_anchor_loo.csv"
    df_loo.to_csv(loo_csv, index=False, encoding="utf-8")
    print(f"  저장: {loo_csv}")
    return df_loo


def analyze_correlations(df, axes_scores, features):
    """A1: 각 감성 축 × 각 음향 변수 Spearman(주) + Pearson(부).

    §9e: FDR(BH, q<0.05) **그리고** |rho| >= 0.2를 둘 다 통과해야 passes_threshold=True.
    """
    print("\n=== §9b A1: 감성 축 × 음향 변수 상관 ===")
    rows = []

    for axis_name, scores in axes_scores.items():
        for feat in features:
            if feat not in df.columns:
                continue
            mask = df[feat].notna()
            x = np.asarray(scores)[mask.values]
            y = df.loc[mask, feat].astype(float).values
            if len(x) < 3:
                continue
            rho, p_s = stats.spearmanr(x, y)
            r, _ = stats.pearsonr(x, y)
            rows.append({
                "axis": axis_name,
                "feature": feat,
                "role": FEATURE_ROLE.get(feat, "unknown"),
                "spearman_rho": round(float(rho), 4),
                "pearson_r": round(float(r), 4),
                "p": float(p_s),
                "n": int(len(x)),
            })

    df_corr = pd.DataFrame(rows)
    # §9e: FDR은 분석 패밀리(A1)별로 적용
    df_corr["q_fdr"] = bh_fdr(df_corr["p"].values)
    df_corr["passes_fdr"] = df_corr["q_fdr"] < Q_MAX
    df_corr["passes_effect"] = df_corr["spearman_rho"].abs() >= RHO_MIN
    df_corr["passes_threshold"] = df_corr["passes_fdr"] & df_corr["passes_effect"]

    df_corr["p"] = df_corr["p"].map(lambda v: float(f"{v:.6g}"))
    df_corr["q_fdr"] = df_corr["q_fdr"].map(lambda v: float(f"{v:.6g}"))

    out_csv = config.OUT_DIR / "assoc_correlations.csv"
    df_corr.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  {len(df_corr)}개 (축 × 변수) 쌍 검정")
    print(f"  FDR만 통과: {int(df_corr['passes_fdr'].sum())}개")
    print(f"  효과크기(|rho|>={RHO_MIN})만 통과: {int(df_corr['passes_effect'].sum())}개")
    print(f"  §9e 기준(둘 다) 통과: {int(df_corr['passes_threshold'].sum())}개")
    print(f"  저장: {out_csv}")
    return df_corr


# ============================================================================
# A2 (§9c): 카테고리 그룹 대비
# ============================================================================
def analyze_category_contrast(df, features):
    """A2: category1∪category2에서 n>=20 키워드 그룹 vs 나머지 Cohen's d + Mann-Whitney U.

    §9c의 명시적 대비("슬픔 계열" vs "행복 계열")도 별도 행으로 추가한다 -- 이것이
    가사-곡조 불일치의 직접 검정이다.
    """
    print("\n=== §9c A2: 카테고리 그룹 대비 ===")

    # category1 ∪ category2 (곡별 집합 -- 같은 키워드가 양쪽에 있어도 1회)
    kw_sets = [
        {str(r["category1"]).strip(), str(r["category2"]).strip()} - {"nan", ""}
        for _, r in df.iterrows()
    ]
    counts = {}
    for s in kw_sets:
        for k in s:
            counts[k] = counts.get(k, 0) + 1

    keywords = sorted([k for k, c in counts.items() if c >= KEYWORD_MIN_N],
                      key=lambda k: -counts[k])
    print(f"  고유 키워드 {len(counts)}개 중 n>={KEYWORD_MIN_N}: {len(keywords)}개")
    print(f"  대상 키워드: {keywords}")

    rows = []

    def contrast(label, in_mask, features, n_in_note=None):
        for feat in features:
            if feat not in df.columns:
                continue
            valid = df[feat].notna().values
            a = df.loc[in_mask & valid, feat].astype(float).values
            b = df.loc[(~in_mask) & valid, feat].astype(float).values
            if len(a) < 3 or len(b) < 3:
                continue
            d = cohens_d(a, b)
            try:
                _, p = stats.mannwhitneyu(a, b, alternative="two-sided")
            except ValueError:
                continue
            rows.append({
                "keyword": label,
                "n": int(len(a)),
                "n_other": int(len(b)),
                "feature": feat,
                "role": FEATURE_ROLE.get(feat, "unknown"),
                "cohens_d": round(float(d), 4) if not np.isnan(d) else np.nan,
                "mwu_p": float(p),
            })

    # 개별 키워드 그룹 vs 나머지
    for kw in keywords:
        in_mask = np.array([kw in s for s in kw_sets])
        contrast(kw, in_mask, features)

    # §9c 명시적 대비: 슬픔 계열 vs 행복 계열 (나머지 전체가 아니라 두 그룹 간 직접 대비)
    def in_family(s, family):
        return any(any(f in k for f in family) for k in s)

    sad_mask = np.array([in_family(s, SAD_FAMILY) for s in kw_sets])
    happy_mask = np.array([in_family(s, HAPPY_FAMILY) for s in kw_sets])
    # 양쪽에 다 걸리는 곡은 대비에서 제외(모호)
    both = sad_mask & happy_mask
    sad_only = sad_mask & ~both
    happy_only = happy_mask & ~both
    print(f"  [명시적 대비] 슬픔 계열 {int(sad_only.sum())}곡 vs 행복 계열 "
          f"{int(happy_only.sum())}곡 (양쪽 중복 제외 {int(both.sum())}곡)")

    for feat in features:
        if feat not in df.columns:
            continue
        valid = df[feat].notna().values
        a = df.loc[sad_only & valid, feat].astype(float).values
        b = df.loc[happy_only & valid, feat].astype(float).values
        if len(a) < 3 or len(b) < 3:
            continue
        d = cohens_d(a, b)
        _, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        rows.append({
            "keyword": "__SAD_FAMILY_vs_HAPPY_FAMILY__",
            "n": int(len(a)),
            "n_other": int(len(b)),
            "feature": feat,
            "role": FEATURE_ROLE.get(feat, "unknown"),
            "cohens_d": round(float(d), 4) if not np.isnan(d) else np.nan,
            "mwu_p": float(p),
        })

    df_cat = pd.DataFrame(rows)
    # §9e: FDR은 분석 패밀리(A2)별로 적용
    df_cat["q_fdr"] = bh_fdr(df_cat["mwu_p"].values)
    df_cat["passes_fdr"] = df_cat["q_fdr"] < Q_MAX
    df_cat["passes_effect"] = df_cat["cohens_d"].abs() >= D_MIN
    df_cat["passes_threshold"] = df_cat["passes_fdr"] & df_cat["passes_effect"]

    df_cat["mwu_p"] = df_cat["mwu_p"].map(lambda v: float(f"{v:.6g}"))
    df_cat["q_fdr"] = df_cat["q_fdr"].map(lambda v: float(f"{v:.6g}"))

    out_csv = config.OUT_DIR / "assoc_category_contrast.csv"
    df_cat.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  {len(df_cat)}개 (키워드 × 변수) 검정")
    print(f"  §9e 기준(FDR + |d|>={D_MIN}) 통과: {int(df_cat['passes_threshold'].sum())}개")
    print(f"  저장: {out_csv}")
    return df_cat


# ============================================================================
# A3 (§9d): 예측 상한 (ceiling)
# ============================================================================
def analyze_ceiling(df, desc_vecs, axes_scores, features):
    """A3: desc 임베딩(1024차원) -> 각 음향 변수 Ridge 회귀 out-of-fold R².

    §9d 요건:
      - in-sample R² 보고 금지. 반드시 out-of-fold 예측 기준.
      - Ridge alpha는 fold 내부에서 선택(중첩 CV, 누수 방지).
      - KFold(5, shuffle, random_state=SEED) / GroupKFold(5, groups=band) 둘 다 보고.
      - 역방향(음향 전체 -> lyr_valence/lyr_arousal)도 동일 프로토콜.
    """
    print("\n=== §9d A3: 예측 상한 (out-of-fold R²) ===")

    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, GroupKFold, GridSearchCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import r2_score

    ALPHAS = [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
    bands = df["band"].values

    def oof_r2(X, y, splitter, groups=None):
        """중첩 CV: 바깥 fold로 OOF 예측, alpha는 안쪽 fold에서 선택."""
        oof = np.full(len(y), np.nan)
        split_iter = (splitter.split(X, y, groups=groups) if groups is not None
                      else splitter.split(X, y))
        for tr, te in split_iter:
            # 내부 CV: train만 사용 -> 누수 없음
            inner = KFold(5, shuffle=True, random_state=config.SEED)
            pipe = Pipeline([("sc", StandardScaler()), ("rg", Ridge())])
            gs = GridSearchCV(pipe, {"rg__alpha": ALPHAS}, cv=inner,
                              scoring="r2", n_jobs=-1)
            gs.fit(X[tr], y[tr])
            oof[te] = gs.predict(X[te])
        return float(r2_score(y, oof))

    rows = []

    # --- 정방향: desc 임베딩 -> 음향 변수 ---
    for feat in features:
        if feat not in df.columns:
            continue
        mask = df[feat].notna().values
        X = desc_vecs[mask]
        y = df.loc[mask, feat].astype(float).values
        g = bands[mask]
        if len(y) < 50:
            continue

        kf = KFold(5, shuffle=True, random_state=config.SEED)
        r2_kf = oof_r2(X, y, kf)
        gkf = GroupKFold(5)
        r2_gkf = oof_r2(X, y, gkf, groups=g)

        rows.append({
            "direction": "desc_emb -> acoustic",
            "target": feat,
            "role": FEATURE_ROLE.get(feat, "unknown"),
            "n": int(len(y)),
            "r2_kfold": round(r2_kf, 4),
            "r2_groupkfold": round(r2_gkf, 4),
            "gap": round(r2_kf - r2_gkf, 4),
        })
        print(f"  {feat:22s} r2_kfold={r2_kf:+.4f}  r2_groupkfold={r2_gkf:+.4f}  "
              f"gap={r2_kf - r2_gkf:+.4f}")

    # --- 역방향: 음향 변수 전체 -> 감성 축 ---
    acou_cols = [f for f in features if f in df.columns]
    A = df[acou_cols].astype(float)
    # 결측은 중앙값 대치(역방향 X는 저차원이라 행 삭제보다 대치가 적절)
    n_na = int(A.isna().sum().sum())
    if n_na:
        print(f"  [역방향] 음향 X 결측 {n_na}건 -> 중앙값 대치")
    A = A.fillna(A.median()).values

    for axis_name, scores in axes_scores.items():
        y = np.asarray(scores, dtype=float)
        kf = KFold(5, shuffle=True, random_state=config.SEED)
        r2_kf = oof_r2(A, y, kf)
        gkf = GroupKFold(5)
        r2_gkf = oof_r2(A, y, gkf, groups=bands)
        rows.append({
            "direction": "acoustic -> lyr_axis",
            "target": axis_name,
            "role": "emotion_axis",
            "n": int(len(y)),
            "r2_kfold": round(r2_kf, 4),
            "r2_groupkfold": round(r2_gkf, 4),
            "gap": round(r2_kf - r2_gkf, 4),
        })
        print(f"  {axis_name:22s} r2_kfold={r2_kf:+.4f}  r2_groupkfold={r2_gkf:+.4f}  "
              f"gap={r2_kf - r2_gkf:+.4f}  [역방향]")

    df_ceil = pd.DataFrame(rows)
    out_csv = config.OUT_DIR / "assoc_ceiling.csv"
    df_ceil.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  저장: {out_csv}")
    return df_ceil


# ============================================================================
# A4 (§9f): 설문 교차검증 준비 -- 지표 계산 후 저장만
# ============================================================================
def build_alignment(df, axes_scores):
    """A4: 곡별 불일치 지표를 사전 계산해 저장.

    mismatch_arousal = |percentile(lyr_arousal) - intensity_pct|
      -> intensity는 §1a에서 검증된 축이므로 근거가 탄탄하다.
    mismatch_valence_weak = |percentile(lyr_valence) - brightness_pct|
      -> valence 쪽은 검증된 음향 축이 없다(§1b). mode_score는 장/단조 축일 뿐이므로
         **약한 대리 지표**이며 이름에 _weak를 붙여 별도 취급한다.

    §9f: 사람 점수와의 검정은 설문 채점이 끝난 뒤에 수행한다. 지금은 지표만 저장한다.
    지표 정의를 결과를 본 뒤에 바꾸는 것은 금지.
    """
    print("\n=== §9f A4: 불일치 지표 계산 (저장만, 검정 없음) ===")

    rank_val = percentile_ranker(list(axes_scores["lyr_valence"]))
    rank_aro = percentile_ranker(list(axes_scores["lyr_arousal"]))

    out = pd.DataFrame({
        "tag": df["tag"].values,
        "lyr_valence_pct": [rank_val(v) for v in axes_scores["lyr_valence"]],
        "lyr_arousal_pct": [rank_aro(v) for v in axes_scores["lyr_arousal"]],
        "intensity_pct": df["intensity_pct"].values,
        "brightness_pct": df["brightness_pct"].values,
    })
    out["mismatch_arousal"] = (out["lyr_arousal_pct"] - out["intensity_pct"]).abs()
    out["mismatch_valence_weak"] = (out["lyr_valence_pct"] - out["brightness_pct"]).abs()

    out_csv = config.OUT_DIR / "lyrics_acoustic_alignment.csv"
    out.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  {len(out)}행")
    print(f"  mismatch_arousal:      mean={out['mismatch_arousal'].mean():.4f}, "
          f"median={out['mismatch_arousal'].median():.4f}")
    print(f"  mismatch_valence_weak: mean={out['mismatch_valence_weak'].mean():.4f}, "
          f"median={out['mismatch_valence_weak'].median():.4f}")
    print(f"  저장: {out_csv}")
    print("  NOTE: 사람 점수와의 검정은 설문 완료 후 수행(§9f). 블라인드 시트는 열지 않음.")
    return out


def save_emotion_axes(df, axes_scores):
    """§9g: out/lyrics_emotion_axes.csv -- tag, lyr_valence, lyr_arousal + 각 백분위."""
    rank_val = percentile_ranker(list(axes_scores["lyr_valence"]))
    rank_aro = percentile_ranker(list(axes_scores["lyr_arousal"]))
    out = pd.DataFrame({
        "tag": df["tag"].values,
        "band": df["band"].values,
        "song": df["song"].values,
        "lyr_valence": np.round(axes_scores["lyr_valence"], 6),
        "lyr_arousal": np.round(axes_scores["lyr_arousal"], 6),
        "lyr_valence_pct": [rank_val(v) for v in axes_scores["lyr_valence"]],
        "lyr_arousal_pct": [rank_aro(v) for v in axes_scores["lyr_arousal"]],
    })
    out_csv = config.OUT_DIR / "lyrics_emotion_axes.csv"
    out.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  저장: {out_csv} ({len(out)}행)")
    return out


# ============================================================================
# 히트맵 (§9g)
# ============================================================================
def plot_heatmap(df_corr):
    """A1 상관 히트맵(감성 축 × 음향 변수). 효과크기 하한 미달 셀은 회색 처리(§9g)."""
    print("\n=== §9g 히트맵 생성 ===")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm

    axes_order = list(EMOTION_AXES.keys())
    feats = [f for f in ALL_FEATURES if f in set(df_corr["feature"])]

    mat = np.full((len(axes_order), len(feats)), np.nan)
    passed = np.zeros_like(mat, dtype=bool)
    for i, ax_name in enumerate(axes_order):
        for j, feat in enumerate(feats):
            sel = df_corr[(df_corr["axis"] == ax_name) & (df_corr["feature"] == feat)]
            if len(sel):
                mat[i, j] = sel.iloc[0]["spearman_rho"]
                passed[i, j] = bool(sel.iloc[0]["passes_threshold"])

    fig, ax = plt.subplots(figsize=(max(10, len(feats) * 0.45), 3.4))

    # 하한 미달 셀은 회색 -- 통과 셀만 발산형 컬러맵으로 표시(§9g)
    ax.imshow(np.zeros_like(mat), cmap="Greys", vmin=0, vmax=1, aspect="auto")
    masked = np.ma.masked_where(~passed, mat)
    cmap = plt.get_cmap("RdBu_r").copy()
    norm = TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1)
    im = ax.imshow(masked, cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(range(len(feats)))
    ax.set_xticklabels(feats, rotation=90, fontsize=7)
    ax.set_yticks(range(len(axes_order)))
    ax.set_yticklabels(axes_order, fontsize=9)

    # 음성 대조군 라벨을 표시해 눈으로 바로 구분되게 한다.
    for j, feat in enumerate(feats):
        if FEATURE_ROLE.get(feat) == "negative_control":
            ax.get_xticklabels()[j].set_color("red")

    for i in range(len(axes_order)):
        for j in range(len(feats)):
            if np.isnan(mat[i, j]):
                continue
            txt = f"{mat[i, j]:.2f}".replace("0.", ".")
            ax.text(j, i, txt, ha="center", va="center", fontsize=6,
                    color="black" if passed[i, j] else "#888888")

    ax.set_title(
        f"A1: lyrics emotion axis x acoustic feature (Spearman rho, n=661)\n"
        f"grey = fails §9e gate (FDR q<{Q_MAX} AND |rho|>={RHO_MIN});  "
        f"red label = negative control",
        fontsize=9,
    )
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01, label="Spearman rho")
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig_path = FIG_DIR / "assoc_heatmap.png"
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  저장: {fig_path}")
    return fig_path


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = {"step": "lyrics_acoustic_assoc",
                "started_at": datetime.now(timezone.utc).isoformat()}
    save_progress(progress, status="in_progress")

    df = load_data()
    save_progress(progress, status="in_progress", stage="data_loaded", n_rows=len(df))

    print(f"임베딩 모델 로드: {config.EMBED_MODEL}")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(config.EMBED_MODEL)

    desc_vecs, axes_scores = build_emotion_axes(df, model)
    save_emotion_axes(df, axes_scores)
    save_progress(progress, status="in_progress", stage="A1_axes_done")

    # §9h 앵커 민감도 -- 축을 쓰기 전에 확인
    anchor_loo_sensitivity(df, model, desc_vecs)
    save_progress(progress, status="in_progress", stage="anchor_loo_done")

    features = [f for f in ALL_FEATURES if f in df.columns]
    df_corr = analyze_correlations(df, axes_scores, features)
    save_progress(progress, status="in_progress", stage="A1_corr_done")

    df_cat = analyze_category_contrast(df, features)
    save_progress(progress, status="in_progress", stage="A2_done")

    analyze_ceiling(df, desc_vecs, axes_scores, features)
    save_progress(progress, status="in_progress", stage="A3_done")

    build_alignment(df, axes_scores)
    save_progress(progress, status="in_progress", stage="A4_done")

    plot_heatmap(df_corr)
    save_progress(progress, status="done", stage="all_done")

    # 음성 대조군 점검(§9a/§9e) -- 통과하면 파이프라인 오류 신호.
    # §9e의 대조군 조건은 A1/A2 양쪽 패밀리에 모두 걸린다(두 패밀리 각각에 FDR을 적용하므로
    # 대조군 점검도 각각 해야 한다).
    print("\n=== §9e 음성 대조군 점검 ===")

    print("  [A1] 감성 축 × 대조군 변수:")
    nc1 = df_corr[df_corr["role"] == "negative_control"]
    for _, r in nc1.iterrows():
        print(f"    {r['axis']:12s} × {r['feature']:14s} rho={r['spearman_rho']:+.4f}, "
              f"q={r['q_fdr']:.4g}, passes_threshold={r['passes_threshold']}")
    n_pass1 = int(nc1["passes_threshold"].sum())
    print(f"    A1 대조군 통과: {n_pass1} / {len(nc1)}")

    print("  [A2] 키워드 그룹 × 대조군 변수:")
    nc2 = df_cat[df_cat["role"] == "negative_control"]
    nc2_pass = nc2[nc2["passes_threshold"]]
    for _, r in nc2_pass.iterrows():
        print(f"    {r['keyword']} × {r['feature']}: d={r['cohens_d']:+.4f}, "
              f"q={r['q_fdr']:.4g}, n={r['n']}")
    n_pass2 = int(nc2["passes_threshold"].sum())
    print(f"    A2 대조군 통과: {n_pass2} / {len(nc2)}")

    if n_pass1 + n_pass2:
        print(f"\n  *** WARNING: 음성 대조군이 §9e 기준을 통과했다 "
              f"(A1 {n_pass1}건, A2 {n_pass2}건). §9e에 따라 파이프라인 오류를 의심하고, "
              f"원인 규명 전까지 결과를 확정하지 말 것. ***")
    else:
        print("\n  (ok) 음성 대조군이 §9e 기준을 통과하지 않음 -- 파이프라인 오류 신호 없음")

    print("\n--- §9 부속 연구 완료 ---")


if __name__ == "__main__":
    main()
