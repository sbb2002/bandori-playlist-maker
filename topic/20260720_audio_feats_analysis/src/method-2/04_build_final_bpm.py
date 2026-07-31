#!/usr/bin/env python3
"""최종 BPM 통합본 산출 — 이 topic의 템포 축 결론 산출물.

report/02 §3 결론을 그대로 구현한다:
  - bestdori 매칭곡(573곡): 공식 BPM 채용 (bpm_source=official)
  - 미매칭곡(88곡): "[85,220] 내 최대 후보" 규칙 추정치 (bpm_source=estimated)

출력: out/bpm_final.csv (661곡 전체, 곡당 final_bpm 1개)
"""
import pandas as pd

from config import (BPM_SELECTED_CSV, BESTDORI_BPM_CSV, BPM_FINAL_CSV,
                    BPM_LO, BPM_HI, OCTAVES)


def max_candidate(base):
    return max(base * 2.0 ** n for n in OCTAVES if BPM_LO <= base * 2.0 ** n <= BPM_HI)


def main():
    sel = pd.read_csv(BPM_SELECTED_CSV)
    off = pd.read_csv(BESTDORI_BPM_CSV)[["idx", "bestdori_id", "official_bpm", "n_unique_bpm"]]
    df = sel[["idx", "tag", "band", "song", "drum_tempo_bpm"]].merge(off, on="idx", how="left")

    df["estimated_bpm"] = df["drum_tempo_bpm"].map(max_candidate)
    df["final_bpm"] = df["official_bpm"].fillna(df["estimated_bpm"])
    df["bpm_source"] = df["official_bpm"].notna().map({True: "official", False: "estimated"})

    df.to_csv(BPM_FINAL_CSV, index=False)
    print(f"total: {len(df)}  (official: {(df.bpm_source == 'official').sum()}, "
          f"estimated: {(df.bpm_source == 'estimated').sum()})")
    print(f"final_bpm range: [{df.final_bpm.min():.1f}, {df.final_bpm.max():.1f}]")
    print("\n밴드별 최고/최저 (검산용):")
    for band, g in df.groupby("band"):
        fast, slow = g.loc[g.final_bpm.idxmax()], g.loc[g.final_bpm.idxmin()]
        print(f"  {band:18s} 최고 {fast.final_bpm:6.1f} {fast.song}")
        print(f"  {'':18s} 최저 {slow.final_bpm:6.1f} {slow.song}")


if __name__ == "__main__":
    main()
