"""GEMS-9 파일럿(n=1, 사용자 본인) 설문 대상곡 선정.

gems_methodology.md §2(1명=통계적 유효성 없음, 파일럿/질적 사례 용도), §3(밴드 편중 방지,
30초 내외 대표구간)에 맞춰 밴드당 N곡을 뽑는다. 곡 선정은 무작위가 아니라 밴드 내
energy_full(이미 검증된 강도축) 최저/중간/최고로 뽑아 — 그 밴드가 가진 감정 폭을 최대한
넓게 커버해야 n=1 파일럿에서도 분산이 나온다. 대표구간(시작/종료초)·GEMS-9 채점은 사용자가
직접 채운다 — 이 스크립트는 후보곡 뼈대만 만든다.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
FEATS_PATH = ROOT / "topic" / "audio_feats_analysis" / "out" / "audio_feats.csv"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "gems9_pilot_candidates.csv"

N_PER_BAND = 3

# GEMS-9 항목 (Zentner et al. 2008) — 상위요인: Sublimity(경이~평온) / Vitality(웅장~활기) / Unease(긴장~슬픔)
GEMS9_ITEMS = [
    "wonder",              # 경이/경탄 — Sublimity
    "transcendence",       # 초월/숭고함 — Sublimity
    "tenderness",          # 다정함/애틋함 — Sublimity
    "nostalgia",           # 향수/그리움 — Sublimity
    "peacefulness",        # 평온함 — Sublimity
    "power",               # 웅장함/강렬함 — Vitality
    "joyful_activation",   # 활기찬 기쁨 — Vitality
    "tension",             # 긴장/불안 — Unease
    "sadness",             # 슬픔 — Unease
]


def load_rows():
    rows = list(csv.DictReader(open(FEATS_PATH, encoding="utf-8")))
    return [r for r in rows if r.get("eligible_band") == "True" and r.get("energy_full")]


def pick_band_representatives(rows, n_per_band):
    by_band = {}
    for r in rows:
        by_band.setdefault(r["band"], []).append(r)

    picked = []
    for band, songs in by_band.items():
        songs.sort(key=lambda r: float(r["energy_full"]))
        n = len(songs)
        if n <= n_per_band:
            picked.extend(songs)
            continue
        # 최저 / 중간 / 최고 (n_per_band=3 기준). n_per_band가 다르면 등간격 인덱스로 확장.
        idxs = sorted({round(i * (n - 1) / (n_per_band - 1)) for i in range(n_per_band)})
        picked.extend(songs[i] for i in idxs)
    return picked


def main():
    rows = load_rows()
    picked = pick_band_representatives(rows, N_PER_BAND)
    picked.sort(key=lambda r: (r["band"], float(r["energy_full"])))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = (
        ["idx", "band", "song", "url", "energy_full",
         "excerpt_start_sec", "excerpt_end_sec"]
        + GEMS9_ITEMS
        + ["rater_note"]
    )
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in picked:
            w.writerow(
                [r["idx"], r["band"], r["song"], r["url"], r["energy_full"], "", ""]
                + [""] * len(GEMS9_ITEMS)
                + [""]
            )

    print(f"{len(picked)}곡 선정 -> {OUT_PATH}")
    from collections import Counter
    for band, n in Counter(r["band"] for r in picked).most_common():
        print(f"  {band}: {n}곡")


if __name__ == "__main__":
    main()
