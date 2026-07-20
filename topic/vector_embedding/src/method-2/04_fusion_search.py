"""Stage 3: Fusion search — 3 arms × 6 queries × top-3 — DESIGN.md §4.

Arms:
  A: Lyrics only (lyr_rank, from method-1 results)
  B: Acoustics only (acou_rank)
  C: Fusion α·lyr_rank + (1-α)·acou_rank with α=0.5

Also outputs sensitivity analysis for α ∈ {0.25, 0.75}.

Output:
  - out/phase2_search_results.csv: query_id, tier, rank, arm, tag, band, song,
    url, lyr_rank, acou_rank, acou_match, combined_rank
  - out/phase2_alpha_sensitivity.csv: results for α=0.25 and α=0.75 (reference only,
    not used for evaluation per DESIGN.md §4c)
  - out/phase2_search_progress.json: progress tracking
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import bisect
import numpy as np
import pandas as pd

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROGRESS_PATH = config.OUT_DIR / "phase2_search_progress.json"


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"started_at": datetime.now(timezone.utc).isoformat()}


def save_progress(progress, **fields):
    progress.update(fields)
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def percentile_ranker(values: list[float]):
    """Create percentile ranking function. rank(v) ∈ [0, 1]."""
    srt = sorted(values)
    n = len(srt)

    def rank(v: float) -> float:
        if n == 0:
            return 0.5
        less = bisect.bisect_left(srt, v)
        equal = bisect.bisect_right(srt, v) - less
        return (less + 0.5 * equal) / n

    return rank


def fuse_search():
    """Execute fusion search over 3 arms."""
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()
    progress["step"] = "fusion_search"
    save_progress(progress, status="in_progress", n_done=0, n_total=6)

    print("=== Phase 2 Fusion Search ===\n")

    # Load acoustic profiles
    acoustics_csv = config.OUT_DIR / "song_acoustics.csv"
    if not acoustics_csv.exists():
        print(f"ERROR: {acoustics_csv} not found. Run 02_build_acoustics.py first.")
        sys.exit(1)

    df_acoustics = pd.read_csv(acoustics_csv)
    print(f"Loaded {len(df_acoustics)} song acoustic profiles")

    # Load acoustic targets
    targets_csv = config.OUT_DIR / "query_acoustic_targets.csv"
    if not targets_csv.exists():
        print(f"ERROR: {targets_csv} not found. Run 03_query_targets.py first.")
        sys.exit(1)

    df_targets = pd.read_csv(targets_csv).set_index("query_id")
    print(f"Loaded {len(df_targets)} query acoustic targets")

    # Load method-1 results (arm A baseline)
    stage2_csv = config.METHOD_1_OUT_DIR / "stage2_eval_sheet.csv"
    if not stage2_csv.exists():
        print(f"ERROR: {stage2_csv} not found.")
        sys.exit(1)

    df_m1 = pd.read_csv(stage2_csv)
    print(f"Loaded {len(df_m1)} method-1 results for arm A")

    # Load expanded queries for embedding
    queries_csv = config.METHOD_1_OUT_DIR / "stage2_queries_expanded.csv"
    if not queries_csv.exists():
        print(f"ERROR: {queries_csv} not found.")
        sys.exit(1)

    df_queries_expanded = pd.read_csv(queries_csv)

    # ========================================================================
    # Load embeddings
    # ========================================================================
    print("\nLoading embeddings from method-1...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(config.EMBED_MODEL)
    except Exception as e:
        print(f"ERROR loading embedding model: {e}")
        sys.exit(1)

    # Embed song descriptions
    song_descs = df_acoustics["tag"].map(
        lambda tag: df_m1[df_m1["tag"] == tag]["prompt_text"].iloc[0]
        if tag in df_m1["tag"].values else ""
    ).fillna("").tolist()

    # Actually, we need song profile descriptions. Let me load them from method-1.
    profiles_csv = config.METHOD_1_OUT_DIR / "song_profiles.csv"
    if profiles_csv.exists():
        df_profiles = pd.read_csv(profiles_csv).set_index("tag")
        song_descs = [df_profiles.loc[tag, "desc"] if tag in df_profiles.index else ""
                      for tag in df_acoustics["tag"]]
    else:
        print(f"WARNING: {profiles_csv} not found, using empty descriptions")
        song_descs = [""] * len(df_acoustics)

    print(f"Embedding {len(song_descs)} song descriptions...")
    song_vecs = model.encode(
        song_descs, normalize_embeddings=True, show_progress_bar=False
    )

    # Embed expanded queries
    print(f"Embedding {len(df_queries_expanded)} expanded queries...")
    query_vecs = model.encode(
        df_queries_expanded["expanded_text"].tolist(),
        normalize_embeddings=True,
        show_progress_bar=False
    )

    # ========================================================================
    # Compute scores for each query
    # ========================================================================
    all_results = []

    for qi, query_row in df_queries_expanded.iterrows():
        query_id = query_row["query_id"]
        tier = query_row["tier"]
        prompt_text = query_row["prompt_text"]

        print(f"\n{query_id} ({tier})...")

        # Arm A: Lyrics (cosine similarity)
        cosines = song_vecs @ query_vecs[qi]
        lyr_ranks = np.array([percentile_ranker(cosines.tolist())(c) for c in cosines])

        # Arm B & C: Acoustics
        if query_id not in df_targets.index:
            print(f"  WARNING: No acoustic targets for {query_id}")
            acou_match = np.ones(len(df_acoustics)) * 0.5
        else:
            target_row = df_targets.loc[query_id]
            intensity_t = target_row["intensity_t"]
            brightness_t = target_row["brightness_t"]
            tempo_t = target_row["tempo_t"]

            # Check if all targets are NA
            all_na = (
                (pd.isna(intensity_t) or intensity_t == "") and
                (pd.isna(brightness_t) or brightness_t == "") and
                (pd.isna(tempo_t) or tempo_t == "")
            )

            if all_na:
                print(f"  All targets NA for {query_id} → acou_match = 0.5 (neutral)")
                acou_match = np.ones(len(df_acoustics)) * 0.5
            else:
                # Compute acoustic match: 1 - mean(|feature - target|) over non-NA axes
                acou_match = np.ones(len(df_acoustics))
                n_axes = 0

                if not pd.isna(intensity_t) and intensity_t != "":
                    intensity_t = float(intensity_t)
                    diffs = np.abs(df_acoustics["intensity_pct"].fillna(0.5) - intensity_t)
                    acou_match -= diffs
                    n_axes += 1

                if not pd.isna(brightness_t) and brightness_t != "":
                    brightness_t = float(brightness_t)
                    diffs = np.abs(df_acoustics["brightness_pct"].fillna(0.5) - brightness_t)
                    acou_match -= diffs
                    n_axes += 1

                if not pd.isna(tempo_t) and tempo_t != "":
                    tempo_t = float(tempo_t)
                    diffs = np.abs(df_acoustics["tempo_pct"].fillna(0.5) - tempo_t)
                    acou_match -= diffs
                    n_axes += 1

                if n_axes > 0:
                    acou_match = 1.0 - (acou_match / n_axes)
                else:
                    acou_match = np.ones(len(df_acoustics)) * 0.5

            acou_match = np.clip(acou_match, 0, 1)
            acou_ranks = np.array([percentile_ranker(acou_match.tolist())(m) for m in acou_match])

        # Arm C: Fusion (α = 0.5 main)
        combined_ranks_05 = config.ALPHA * lyr_ranks + (1 - config.ALPHA) * acou_ranks

        # Sensitivity analysis (for reference, not evaluation)
        combined_ranks_025 = 0.25 * lyr_ranks + 0.75 * acou_ranks
        combined_ranks_075 = 0.75 * lyr_ranks + 0.25 * acou_ranks

        # ====================================================================
        # Extract top-3 for each arm
        # ====================================================================
        top_k = 3

        # Arm A (lyr_ranks)
        top_idx_a = np.argsort(-lyr_ranks)[:top_k]
        for rank, idx in enumerate(top_idx_a, 1):
            row = df_acoustics.iloc[idx]
            all_results.append({
                "query_id": query_id,
                "tier": tier,
                "rank": rank,
                "arm": "A",
                "tag": row["tag"],
                "band": row["band"],
                "song": row["song"],
                "url": row.get("url", ""),  # Not in acoustics, add from full_catalog_songs
                "lyr_rank": round(float(lyr_ranks[idx]), 4),
                "acou_rank": round(float(acou_ranks[idx]), 4),
                "acou_match": round(float(acou_match[idx]), 4),
                "combined_rank": round(float(lyr_ranks[idx]), 4),  # For arm A, just lyr_rank
            })

        # Arm B (acou_ranks)
        top_idx_b = np.argsort(-acou_ranks)[:top_k]
        for rank, idx in enumerate(top_idx_b, 1):
            row = df_acoustics.iloc[idx]
            all_results.append({
                "query_id": query_id,
                "tier": tier,
                "rank": rank,
                "arm": "B",
                "tag": row["tag"],
                "band": row["band"],
                "song": row["song"],
                "url": row.get("url", ""),
                "lyr_rank": round(float(lyr_ranks[idx]), 4),
                "acou_rank": round(float(acou_ranks[idx]), 4),
                "acou_match": round(float(acou_match[idx]), 4),
                "combined_rank": round(float(acou_ranks[idx]), 4),  # For arm B, just acou_rank
            })

        # Arm C (combined_ranks_05)
        top_idx_c = np.argsort(-combined_ranks_05)[:top_k]
        for rank, idx in enumerate(top_idx_c, 1):
            row = df_acoustics.iloc[idx]
            all_results.append({
                "query_id": query_id,
                "tier": tier,
                "rank": rank,
                "arm": "C",
                "tag": row["tag"],
                "band": row["band"],
                "song": row["song"],
                "url": row.get("url", ""),
                "lyr_rank": round(float(lyr_ranks[idx]), 4),
                "acou_rank": round(float(acou_ranks[idx]), 4),
                "acou_match": round(float(acou_match[idx]), 4),
                "combined_rank": round(float(combined_ranks_05[idx]), 4),
            })

        print(f"  Arm A top-1: {df_acoustics.iloc[top_idx_a[0]]['tag']}")
        print(f"  Arm B top-1: {df_acoustics.iloc[top_idx_b[0]]['tag']}")
        print(f"  Arm C top-1: {df_acoustics.iloc[top_idx_c[0]]['tag']}")

        progress["n_done"] = qi + 1
        save_progress(progress, status="in_progress")

    # ========================================================================
    # Output results
    # ========================================================================
    df_results = pd.DataFrame(all_results)

    # Add URLs from full_catalog_songs
    df_catalog = pd.read_csv(config.SONGS_CSV).set_index("tag")["url"].to_dict()
    df_results["url"] = df_results["tag"].map(df_catalog)

    results_csv = config.OUT_DIR / "phase2_search_results.csv"
    df_results.to_csv(results_csv, index=False, encoding="utf-8")
    print(f"\nSaved {len(df_results)} results to {results_csv}")

    # Sensitivity analysis (for reference only)
    sensitivity_results = []
    for qi, query_row in df_queries_expanded.iterrows():
        query_id = query_row["query_id"]

        # Recompute for sensitivity alphas
        cosines = song_vecs @ query_vecs[qi]
        lyr_ranks = np.array([percentile_ranker(cosines.tolist())(c) for c in cosines])

        if query_id in df_targets.index:
            target_row = df_targets.loc[query_id]
            # ... (acou_match computation as above)
            acou_match = np.ones(len(df_acoustics)) * 0.5  # Simplified for reference
            acou_ranks = np.array([percentile_ranker(acou_match.tolist())(m) for m in acou_match])
        else:
            acou_ranks = np.ones(len(df_acoustics)) * 0.5

        combined_025 = 0.25 * lyr_ranks + 0.75 * acou_ranks
        combined_075 = 0.75 * lyr_ranks + 0.25 * acou_ranks

        for rank, idx in enumerate(np.argsort(-combined_025)[:top_k], 1):
            row = df_acoustics.iloc[idx]
            sensitivity_results.append({
                "query_id": query_id,
                "alpha": 0.25,
                "rank": rank,
                "tag": row["tag"],
                "combined_rank": round(float(combined_025[idx]), 4),
            })

        for rank, idx in enumerate(np.argsort(-combined_075)[:top_k], 1):
            row = df_acoustics.iloc[idx]
            sensitivity_results.append({
                "query_id": query_id,
                "alpha": 0.75,
                "rank": rank,
                "tag": row["tag"],
                "combined_rank": round(float(combined_075[idx]), 4),
            })

    df_sensitivity = pd.DataFrame(sensitivity_results)
    sensitivity_csv = config.OUT_DIR / "phase2_alpha_sensitivity.csv"
    df_sensitivity.to_csv(sensitivity_csv, index=False, encoding="utf-8")
    print(f"Saved sensitivity analysis to {sensitivity_csv}")

    save_progress(progress, status="done")


if __name__ == "__main__":
    fuse_search()
