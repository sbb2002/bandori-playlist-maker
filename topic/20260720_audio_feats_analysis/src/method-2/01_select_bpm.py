#!/usr/bin/env python3
"""Unified single-candidate BPM selection over all 661 songs (report/01 §6.2-1).

drum_tempo_bpm × 2^n (n=-1..1) 후보 중 [85,220] 범위에 드는 것들을 놓고,
기존 ACF 컬럼(pulse_acf_slow/fast/half)만으로 곡마다 최종 BPM 1개를 선출한다.
오디오 재계산 없음 — 순수 CSV 처리.

선출 규칙(τ=0.96, 형제 프로젝트와 대칭 통일):
  - 후보 1개  -> 그대로 채택 (rule=unique; base가 범위 밖이면 base_in_range=False로 플래그)
  - 후보 {base, base*2} -> pulse_ratio      >= τ 이면 base*2, 아니면 base (rule=acf_up)
  - 후보 {base, base/2} -> pulse_ratio_down >= τ 이면 base/2, 아니면 base (rule=acf_down)
"""
import pandas as pd

from config import AUDIO_FEATS_CSV, BPM_SELECTED_CSV, BPM_LO, BPM_HI, OCTAVES, TAU


def candidates(base_bpm):
    return [n for n in OCTAVES if BPM_LO <= base_bpm * (2 ** n) <= BPM_HI]


def select_row(row):
    base = row["drum_tempo_bpm"]
    cands = candidates(base)
    assert 1 <= len(cands) <= 2, f"{row['tag']}: unexpected candidate set {cands}"

    if len(cands) == 1:
        n = cands[0]
        return n, "unique", None
    if cands == [0, 1]:
        ratio = row["pulse_ratio"]
        return (1 if ratio >= TAU else 0), "acf_up", ratio
    if cands == [-1, 0]:
        ratio = row["pulse_ratio_down"]
        assert pd.notna(ratio), f"{row['tag']}: pulse_ratio_down missing for down-ambiguous song"
        return (-1 if ratio >= TAU else 0), "acf_down", ratio
    raise AssertionError(f"{row['tag']}: unexpected candidate set {cands}")


def main():
    df = pd.read_csv(AUDIO_FEATS_CSV)
    out = []
    for _, row in df.iterrows():
        n, rule, ratio = select_row(row)
        base = row["drum_tempo_bpm"]
        out.append({
            "idx": row["idx"],
            "tag": row["tag"],
            "band": row["band"],
            "song": row["song"],
            "drum_tempo_bpm": base,
            "n_candidates": len(candidates(base)),
            "rule": rule,
            "decision_ratio": ratio,
            "octave_shift": n,
            "selected_bpm": base * (2 ** n),
            "base_in_range": BPM_LO <= base <= BPM_HI,
        })
    res = pd.DataFrame(out)
    res.to_csv(BPM_SELECTED_CSV, index=False)

    print(f"total: {len(res)}")
    print(res["rule"].value_counts().to_string())
    print("octave_shift:")
    print(res["octave_shift"].value_counts().sort_index().to_string())
    flagged = res[~res["base_in_range"]]
    print(f"base out of [{BPM_LO},{BPM_HI}] (folded without ACF evidence): {len(flagged)}")
    if len(flagged):
        print(flagged[["tag", "band", "song", "drum_tempo_bpm", "selected_bpm"]].to_string(index=False))


if __name__ == "__main__":
    main()
