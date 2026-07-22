"""framework.md §2c 재검토 보류 항목 확인 — party(gt dimension)가 intensity의 하위집합인지 점검.

데이터 소스: data/ground_truth_labels.csv (idx,band,song,dimension,label),
            topic/audio_feats_analysis/out/audio_feats.csv (energy_full 등).
청취 불필요 — 기존 라벨·기존 피쳐 대조만 수행.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GT_PATH = ROOT / "data" / "ground_truth_labels.csv"
FEATS_PATH = ROOT / "topic" / "audio_feats_analysis" / "out" / "audio_feats.csv"


def load_gt():
    rows = list(csv.DictReader(open(GT_PATH, encoding="utf-8")))
    by_dim = {}
    for r in rows:
        by_dim.setdefault(r["dimension"], {})[(r["idx"], r["band"], r["song"])] = r["label"]
    return by_dim


def load_energy_full():
    rows = list(csv.DictReader(open(FEATS_PATH, encoding="utf-8")))
    out = {}
    for r in rows:
        key = (r["idx"], r["band"], r["song"])
        try:
            out[key] = float(r["energy_full"])
        except (ValueError, KeyError):
            pass
    return out


def main():
    by_dim = load_gt()
    party = by_dim.get("party", {})
    intensity = by_dim.get("intensity", {})
    energy_full = load_energy_full()

    print(f"party 라벨 {len(party)}건, intensity 라벨 {len(intensity)}건")

    # 1) 같은 곡이 두 dimension 모두에 라벨링됐는지 (직접 겹침)
    overlap_keys = set(party) & set(intensity)
    print(f"두 dimension 모두 라벨링된 곡: {len(overlap_keys)}건")
    for k in sorted(overlap_keys):
        print(f"  {k} party={party[k]} intensity={intensity[k]}")

    # 2) party 라벨 곡의 energy_full 분포 (report/02 §2a 재확인, 개별곡 단위)
    print("\nparty/calm 라벨별 energy_full (개별곡):")
    matched, missing = 0, 0
    party_vals, calm_vals = [], []
    for k, label in party.items():
        ef = energy_full.get(k)
        if ef is None:
            missing += 1
            continue
        matched += 1
        print(f"  {k} label={label} energy_full={ef:.3f}")
        (party_vals if label == "party" else calm_vals).append(ef)

    print(f"\n매칭 {matched}건, energy_full 없음 {missing}건")
    if party_vals and calm_vals:
        print(f"party 평균 energy_full = {sum(party_vals)/len(party_vals):.3f} (n={len(party_vals)})")
        print(f"calm  평균 energy_full = {sum(calm_vals)/len(calm_vals):.3f} (n={len(calm_vals)})")


if __name__ == "__main__":
    main()
