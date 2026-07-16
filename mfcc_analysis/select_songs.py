"""Step 1 — pick 3 songs per band for MFCC comparison.

Selection rule (deterministic, no RNG): for each band, sort candidates by idx
and take the first 3 that have >=90s of audio available locally in
bandori-song-sorter/audio_full; if a band has zero local files, mark all 3
picks as needing download (largest-idx-first is irrelevant — we just take the
first 3 rows for that band in songs_full.csv).

various_artists / ikka_dumb_rock / millsage are excluded — not "bands" in the
sense the playlist maker treats them (compilation / single-song tags).
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SONGS_CSV = os.path.join(HERE, "..", "..", "data", "songs_full.csv")
AUDIO_DIR = r"C:\Users\user\Documents\myprojects\bandori-song-sorter\src\content\cluster\audio_full"
OUT_CSV = os.path.join(HERE, "selected_songs.csv")

EXCLUDE_BANDS = {"various_artists", "ikka_dumb_rock", "millsage"}
N_PER_BAND = 3


def main():
    df = pd.read_csv(SONGS_CSV)
    df = df[~df["band"].isin(EXCLUDE_BANDS)].copy()

    rows = []
    for band, grp in df.groupby("band", sort=True):
        grp = grp.sort_values("idx")
        picked = grp.head(N_PER_BAND)
        for _, r in picked.iterrows():
            tag = f"{band}__{int(r['idx']):03d}"
            local_path = os.path.join(AUDIO_DIR, tag + ".wav")
            rows.append({
                "band": band,
                "idx": int(r["idx"]),
                "song": r["song"],
                "url": r["url"],
                "tag": tag,
                "has_local_audio": os.path.isfile(local_path),
            })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"[select] {len(out)} songs across {out['band'].nunique()} bands")
    print(out.groupby("band")["has_local_audio"].agg(["sum", "count"]))
    missing = out[~out["has_local_audio"]]
    print(f"\n[select] need download: {len(missing)}")
    for _, r in missing.iterrows():
        print(f"  {r['tag']}  {r['url']}")


if __name__ == "__main__":
    main()
