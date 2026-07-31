"""
Step 2: Compute band_pct (intensity percentile within each band).

DESIGN.md §1: band_pct = that song's intensity percentile within its own band population.
This is distinct from intensity_pct in song_acoustics.csv, which is 661-song global percentile.

Output: out/song_band_percentiles.csv
  Columns: tag, band, intensity, band_pct
"""
import sys
from pathlib import Path

import pandas as pd

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def compute_band_percentiles():
    """
    Read song_acoustics.csv, compute intensity percentile within each band,
    and save to out/song_band_percentiles.csv.
    """
    print("Loading song_acoustics.csv...")
    df_acoustics = pd.read_csv(config.SONG_ACOUSTICS_CSV)
    print(f"  Loaded {len(df_acoustics)} songs")

    # Extract relevant columns
    df = df_acoustics[["tag", "band", "intensity"]].copy()

    # Compute intensity percentile within each band
    # Using rank(method='average', pct=True) to handle ties consistently
    print("\nComputing band-level intensity percentiles...")
    df["band_pct"] = df.groupby("band")["intensity"].rank(method="average", pct=True)

    # Round to 4 decimal places for readability
    df["band_pct"] = df["band_pct"].round(4)
    df["intensity"] = df["intensity"].round(4)

    # Save output
    output_csv = config.OUT_DIR / "song_band_percentiles.csv"
    df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"\nSaved {len(df)} rows to {output_csv}")

    # Print summary by band
    print("\n=== Summary by band (sorted by median band_pct) ===")
    summary = df.groupby("band").agg(
        n_songs=("tag", "count"),
        intensity_min=("intensity", "min"),
        intensity_mean=("intensity", "mean"),
        intensity_median=("intensity", "median"),
        intensity_max=("intensity", "max"),
        band_pct_min=("band_pct", "min"),
        band_pct_median=("band_pct", "median"),
        band_pct_max=("band_pct", "max"),
    ).round(4)
    summary = summary.sort_values("intensity_median", ascending=False)
    print(summary.to_string())

    return df


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Check if output already exists
    output_csv = config.OUT_DIR / "song_band_percentiles.csv"
    if output_csv.exists():
        print(f"Output already exists: {output_csv}")
        df = pd.read_csv(output_csv)
        print(f"Loaded {len(df)} rows")
    else:
        df = compute_band_percentiles()

    print("\n--- BAND PERCENTILE COMPUTATION COMPLETE ---")


if __name__ == "__main__":
    main()
