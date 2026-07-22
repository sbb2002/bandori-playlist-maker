"""framework.md §2b — valence 축 극단층 우선 표집 후보 생성.

valence엔 아직 검증된 신호가 없으므로(§1d), 유일하게 계산 가능한 mode_score를 "표집 도구"로만
쓴다(그 값 자체를 믿는 게 아니라 대비가 큰 후보를 뽑는 용도). 밴드 쏠림 방지를 위해 밴드당
상한을 둔다. report/02가 이미 지적한 반례 앵커(mode_score와 실제 인상이 어긋난 곡)를 강제
포함해 청취자가 "mode_score를 그대로 믿으면 안 된다"는 걸 처음부터 인지하게 한다.

청취/라벨링은 이 스크립트가 하지 않는다 — 후보곡 CSV만 만든다.
"""
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FEATS_PATH = ROOT / "topic" / "audio_feats_analysis" / "out" / "audio_feats.csv"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "valence_candidates.csv"

PER_BAND_CAP = 3
N_PER_SIDE = 15

# report/02 §2b가 확인한 "mode_score가 실제 인상과 어긋난" 반례 — 청취 앵커로 강제 포함
ANCHOR_KEYS = {
    ("375", "poppin_party"),   # Yes! BanG_Dream! — 사용자 점수 10인데 mode_score 백분위 0.04
    ("111", "hello_happy_world"),
    ("109", "hello_happy_world"),
}


def load_rows():
    rows = list(csv.DictReader(open(FEATS_PATH, encoding="utf-8")))
    return [r for r in rows if r.get("eligible_band") == "True"]


def pick_extremes(rows, key, n_per_side, per_band_cap):
    valid = [r for r in rows if r.get(key)]
    valid.sort(key=lambda r: float(r[key]))

    def pick(seq, cap):
        picked, band_count = [], Counter()
        for r in seq:
            b = r["band"]
            if band_count[b] >= cap:
                continue
            picked.append(r)
            band_count[b] += 1
            if len(picked) >= n_per_side:
                break
        return picked

    low = pick(valid, per_band_cap)
    high = pick(list(reversed(valid)), per_band_cap)
    return low, high


def main():
    rows = load_rows()
    low, high = pick_extremes(rows, "mode_score", N_PER_SIDE, PER_BAND_CAP)

    chosen = {(r["idx"], r["band"]): (r, "low_mode_score") for r in low}
    chosen.update({(r["idx"], r["band"]): (r, "high_mode_score") for r in high})

    by_key = {(r["idx"], r["band"]): r for r in rows}
    for k in ANCHOR_KEYS:
        if k in by_key and k not in chosen:
            chosen[k] = (by_key[k], "anchor_known_mismatch")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["idx", "band", "song", "url", "mode_score", "energy_full", "pick_reason", "valence_rating_1to10", "listener_note"])
        for (idx, band), (r, reason) in sorted(chosen.items(), key=lambda kv: float(kv[1][0]["mode_score"])):
            w.writerow([idx, band, r["song"], r["url"], r["mode_score"], r["energy_full"], reason, "", ""])

    print(f"{len(chosen)}곡 후보 생성 -> {OUT_PATH}")
    print(f"  low_mode_score(어두움 후보): {len(low)}곡")
    print(f"  high_mode_score(밝음 후보): {len(high)}곡")
    print(f"  앵커(기존 반례): {len(ANCHOR_KEYS & set(by_key))}곡")


if __name__ == "__main__":
    main()
