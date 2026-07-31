"""Step 3 (v3): Run Method 1 (build_setlist) vs Method 2 (build_setlist_with_stage_c).

DESIGN_v3.md §4: single forced stage (StageSpec(energy_target=params.start_energy,
song_count=config.K)), same rng seed per query used for BOTH methods (isolates the
Stage C effect from rng noise). Real production song data (data/songs_master.csv via
prod_snapshot/repo/song_repo.py) and real intensity/brightness computation.

Output: out/v3/method_results.csv
  Columns: query_id, method, rank, idx, band, song, energy, url
"""
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd
import config_v3 as config

sys.path.insert(0, str(Path(__file__).parent))
from prod_snapshot.domain import selection, selection_stage_c
from prod_snapshot.domain.models import MoodParameters, StageSpec
from prod_snapshot.repo import song_repo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_csv = config.OUT_DIR / "method_results.csv"
    if output_csv.exists():
        print(f"Output already exists: {output_csv}")
        return

    songs = song_repo.load_songs()
    print(f"Loaded {len(songs)} songs (real production data/songs_master.csv)")

    df_url = pd.read_csv(config.PROD_SNAPSHOT_DIR.parent.parent.parent / "data" / "songs_master.csv")
    idx_to_url = dict(zip(df_url["idx"], df_url["url"]))

    params_rows = {r["query_id"]: r for r in json.loads((config.OUT_DIR / "query_params.json").read_text(encoding="utf-8"))}
    lyric_scores_all = json.loads((config.OUT_DIR / "lyric_scores.json").read_text(encoding="utf-8"))

    query_ids = list(config.QUERIES.keys())
    results = []

    for qi, query_id in enumerate(query_ids):
        row = params_rows[query_id]
        p = row["params"]
        params = MoodParameters(
            brightness=p["brightness"], start_energy=p["start_energy"], end_energy=p["end_energy"],
            stage_count=p["stage_count"], target_minutes=p["target_minutes"],
            interpretation_summary=p.get("interpretation_summary", ""),
            stage_energies=p.get("stage_energies"), tags=p.get("tags"),
            song_type=p.get("song_type", "all"),
        )
        band_filter = set(row["band_filter"]) if row["band_filter"] else None
        stage_specs = [StageSpec(energy_target=params.start_energy, song_count=config.K)]
        lyric_scores = {int(k): v for k, v in lyric_scores_all[query_id].items()}

        seed = config.SEED_BASE + qi
        print(f"\n  {query_id} (band_filter={band_filter or 'NA'}, start_energy={params.start_energy:.2f}, seed={seed})")

        sl1 = selection.build_setlist(
            songs, params, target_seconds=600, band_filter=band_filter,
            stage_specs=stage_specs, rng=random.Random(seed),
        )
        for rank, p1 in enumerate(sl1.picks, 1):
            results.append({
                "query_id": query_id, "method": "method1", "rank": rank,
                "idx": p1.idx, "band": p1.band, "song": p1.song,
                "energy": round(p1.energy, 4), "url": idx_to_url.get(p1.idx, ""),
            })
        print(f"    Method1: {[(p1.band, p1.song) for p1 in sl1.picks]}")

        sl2 = selection_stage_c.build_setlist_with_stage_c(
            songs, params, target_seconds=600, band_filter=band_filter,
            stage_specs=stage_specs, rng=random.Random(seed), lyric_scores=lyric_scores,
        )
        for rank, p2 in enumerate(sl2.picks, 1):
            results.append({
                "query_id": query_id, "method": "method2", "rank": rank,
                "idx": p2.idx, "band": p2.band, "song": p2.song,
                "energy": round(p2.energy, 4), "url": idx_to_url.get(p2.idx, ""),
            })
        print(f"    Method2: {[(p2.band, p2.song) for p2 in sl2.picks]}")

    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nSaved {len(df)} rows to {output_csv}")
    print(df.groupby("method").size())
    print("unique songs per method:")
    print(df.groupby("method")["idx"].nunique())


if __name__ == "__main__":
    main()
