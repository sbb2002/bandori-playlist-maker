#!/usr/bin/env python3
"""Compare selected BPM vs bestdori official BPM — accuracy + error mean/std.

지표:
  - Accuracy1: |상대오차| <= 4% (옥타브 불허, MIREX 관행)
  - Accuracy2: official×2^n (n=-2..2) 중 가장 가까운 값 기준 |상대오차| <= 4% (옥타브 허용)
  - 오차 통계: signed 상대오차(%)의 mean/std — strict 기준과 octave-folded 기준 각각
부분집합: 전체 매칭곡 / BPM 변화 없는 곡(n_unique_bpm==1)
"""
import numpy as np
import pandas as pd

from config import BPM_SELECTED_CSV, BESTDORI_BPM_CSV, BPM_VALIDATION_CSV, TEMPO_TOL


def summarize(df, label):
    n = len(df)
    acc1 = (df["err_strict_pct"].abs() <= TEMPO_TOL * 100).mean()
    acc2 = (df["err_octave_pct"].abs() <= TEMPO_TOL * 100).mean()
    print(f"\n[{label}] n={n}")
    print(f"  Accuracy1 (strict, ±4%) : {acc1:6.1%}")
    print(f"  Accuracy2 (octave, ±4%) : {acc2:6.1%}")
    for col, name in [("err_strict_pct", "strict"), ("err_octave_pct", "octave-folded")]:
        s = df[col]
        print(f"  {name:>14} err%: mean={s.mean():+7.3f}  std={s.std():7.3f}  "
              f"|mean|={s.abs().mean():6.3f}  median={s.median():+7.3f}")


def main():
    sel = pd.read_csv(BPM_SELECTED_CSV)
    off = pd.read_csv(BESTDORI_BPM_CSV)
    df = sel.merge(off, on=["idx", "tag"], how="inner")

    df["err_strict_pct"] = (df["selected_bpm"] - df["official_bpm"]) / df["official_bpm"] * 100

    # 옥타브 허용: official×2^n 중 selected에 가장 가까운(로그 거리) 값 기준 오차
    shifts = np.array([-2, -1, 0, 1, 2], dtype=float)
    folded = df["official_bpm"].values[:, None] * (2.0 ** shifts[None, :])
    dist = np.abs(np.log2(df["selected_bpm"].values[:, None] / folded))
    best = np.argmin(dist, axis=1)
    df["official_folded"] = folded[np.arange(len(df)), best]
    df["fold_shift"] = shifts[best].astype(int)
    df["err_octave_pct"] = (df["selected_bpm"] - df["official_folded"]) / df["official_folded"] * 100

    df["octave_error"] = df["fold_shift"] != 0  # 옥타브 자체를 틀린 곡

    # 대안 규칙(사후 진단에서 발견): [85,220] 내 후보 중 최대값(높은 옥타브) 채택.
    # pulse_ratio가 옥타브 방향 판별력이 없고(true=base 그룹의 ratio가 오히려 높음),
    # 모호곡의 ~96%가 실제로 ×2 정답이라 무조건 위쪽이 ACF τ 규칙보다 정확하다.
    from config import BPM_LO, BPM_HI, OCTAVES
    def max_candidate(base):
        return max(base * 2.0 ** n for n in OCTAVES if BPM_LO <= base * 2.0 ** n <= BPM_HI)
    df["selected_bpm_maxrule"] = df["drum_tempo_bpm"].map(max_candidate)
    df["err_maxrule_pct"] = (df["selected_bpm_maxrule"] - df["official_bpm"]) / df["official_bpm"] * 100

    df.to_csv(BPM_VALIDATION_CSV, index=False)

    summarize(df, "전체 매칭곡")
    summarize(df[df["n_unique_bpm"] == 1], "BPM 변화 없는 곡 (n_unique_bpm=1)")

    s = df["err_maxrule_pct"]
    acc1_max = (s.abs() <= TEMPO_TOL * 100).mean()
    print(f"\n[대안: 최대 후보 규칙] Accuracy1={acc1_max:6.1%}  "
          f"err% mean={s.mean():+.3f}  std={s.std():.3f}  |mean|={s.abs().mean():.3f}")

    print(f"\n옥타브 오류(fold_shift≠0): {df['octave_error'].sum()}곡 / {len(df)}곡")
    print("rule별 Accuracy1:")
    for rule, g in df.groupby("rule"):
        acc1 = (g["err_strict_pct"].abs() <= TEMPO_TOL * 100).mean()
        print(f"  {rule:8s} n={len(g):3d}  acc1={acc1:6.1%}")
    worst = df.loc[df["err_strict_pct"].abs().sort_values(ascending=False).index[:10],
                   ["tag", "song", "drum_tempo_bpm", "selected_bpm", "official_bpm",
                    "rule", "err_strict_pct", "fold_shift"]]
    print("\n오차 상위 10곡:")
    print(worst.to_string(index=False))


if __name__ == "__main__":
    main()
