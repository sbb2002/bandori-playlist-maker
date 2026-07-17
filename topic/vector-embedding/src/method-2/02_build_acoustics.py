"""Stage 1: Build acoustic axes (intensity, brightness, tempo) — DESIGN.md §2.

Replicates the intensity synthesis logic from src/backend/app/repo/song_repo.py.
Formula: intensity(곡) = power_mean_p3([percentile(-acousticness_proxy), energy_full,
    percentile(i_min), percentile(i_mean), percentile(i_end)])
  where power_mean_p3(xs) = (sum(x**3) / len(xs)) ** (1/3)

Output:
  - out/song_acoustics.csv (661 rows): tag, idx, band, song, intensity,
    intensity_pct, brightness_pct, tempo_pct, shape
"""
import bisect
import sys
from pathlib import Path

import pandas as pd
import numpy as np

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Intensity synthesis power (DESIGN.md §2)
_INTENSITY_P = 3


def _percentile_ranker(values: list[float]):
    """Create a percentile ranking function matching song_repo._percentile_ranker.

    rank(v) = (strictly_less_count + 0.5*tied_count) / n ∈ [0,1]
    """
    srt = sorted(values)
    n = len(srt)

    def rank(v: float) -> float:
        if n == 0:
            return 0.5
        less = bisect.bisect_left(srt, v)
        equal = bisect.bisect_right(srt, v) - less
        return (less + 0.5 * equal) / n

    return rank


def build_acoustics():
    """Build acoustic axes for all 661 songs."""
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load master song data
    df_master = pd.read_csv(config.SONGS_MASTER_CSV)
    print(f"Loaded {len(df_master)} songs from songs_master.csv")

    # Build tag column for join
    df_master["tag"] = df_master["band"] + "__" + df_master["idx"].astype(str).str.zfill(3)

    # ========================================================================
    # Step 1: Filter eligible songs for percentile calculation basis
    # ========================================================================
    # Percentiles are based on eligible_band==True only (DESIGN.md §2)
    df_eligible = df_master[df_master["eligible_band"] == True].copy()
    print(f"Found {len(df_eligible)} eligible songs (basis for percentiles)")

    # ========================================================================
    # Step 2: Build intensity signal pool
    # ========================================================================
    # Signal 1: -acousticness_proxy (1=most non-acoustic=loudest)
    acou_values = [-v for v in df_eligible["acousticness_proxy"].dropna().tolist()]
    rank_acoustic = _percentile_ranker(acou_values)

    # Signals 2-4: temporal intensity (i_min, i_mean, i_end) — only if present
    temporal_cols = ["i_min", "i_mean", "i_end"]
    rankers = {}
    for col in temporal_cols:
        if col in df_master.columns:
            vals = df_eligible[col].dropna().tolist()
            if vals:
                rankers[col] = _percentile_ranker(vals)
                print(f"  Ranking {col}: {len(vals)} eligible values")

    # ========================================================================
    # Step 3: Calculate intensity for all songs
    # ========================================================================
    def calc_intensity(row):
        signals = []

        # Signal 1: percentile(-acousticness_proxy)
        ap = (row.get("acousticness_proxy") or "")
        if isinstance(ap, str):
            ap = ap.strip()
        if ap and ap != "":
            try:
                signals.append(rank_acoustic(-float(ap)))
            except (ValueError, TypeError):
                pass

        # Signal 2: energy_full (0~1, no percentile conversion)
        ef = row.get("energy_full")
        if ef is not None and isinstance(ef, (int, float)):
            ef = float(ef)
            if not pd.isna(ef) and ef != "":
                signals.append(ef)
        elif isinstance(ef, str):
            ef = ef.strip()
            if ef:
                try:
                    signals.append(float(ef))
                except (ValueError, TypeError):
                    pass

        # Signals 3-5: temporal intensity percentiles
        for col in temporal_cols:
            if col in rankers:
                val = row.get(col)
                if val is not None and isinstance(val, (int, float)):
                    val = float(val)
                    if not pd.isna(val):
                        signals.append(rankers[col](val))
                elif isinstance(val, str):
                    val = val.strip()
                    if val:
                        try:
                            signals.append(rankers[col](float(val)))
                        except (ValueError, TypeError):
                            pass

        # Compute power mean
        if not signals:
            return np.nan
        p = _INTENSITY_P
        return (sum(s ** p for s in signals) / len(signals)) ** (1.0 / p)

    print("\nCalculating intensity for all 661 songs...")
    df_master["intensity"] = df_master.apply(calc_intensity, axis=1)

    # ========================================================================
    # Step 4: Calculate percentiles (over full 661-song pool for output)
    # ========================================================================
    rank_intensity = _percentile_ranker(df_master["intensity"].dropna().tolist())
    rank_brightness = _percentile_ranker(df_master["mode_score"].dropna().tolist())
    rank_tempo = _percentile_ranker(df_master["bpm"].dropna().tolist())

    df_master["intensity_pct"] = df_master["intensity"].apply(
        lambda x: rank_intensity(x) if pd.notna(x) else np.nan
    )
    df_master["brightness_pct"] = df_master["mode_score"].apply(
        lambda x: rank_brightness(x) if pd.notna(x) else np.nan
    )
    df_master["tempo_pct"] = df_master["bpm"].apply(
        lambda x: rank_tempo(x) if pd.notna(x) else np.nan
    )

    # ========================================================================
    # Step 5: Output
    # ========================================================================
    df_out = df_master[[
        "tag", "idx", "band", "song",
        "intensity", "intensity_pct",
        "brightness_pct", "tempo_pct",
        "shape"
    ]].copy()

    acoustics_csv = config.OUT_DIR / "song_acoustics.csv"
    df_out.to_csv(acoustics_csv, index=False, encoding="utf-8")
    print(f"\nSaved {len(df_out)} song acoustic profiles to {acoustics_csv}")

    # Validation
    print("\n=== Validation ===")
    print(f"Rows: {len(df_out)} (expected 661)")
    print(f"Intensity: min={df_out['intensity'].min():.4f}, max={df_out['intensity'].max():.4f}")
    print(f"Missing intensity: {df_out['intensity'].isna().sum()}")


if __name__ == "__main__":
    build_acoustics()
