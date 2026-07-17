"""Select 19 pilot songs: 16 labeled (bright/dark) + 3 known mismatches.

DESIGN.md §2:
- Load ground_truth_labels.csv, filter dimension=="brightness"
- Extract 8 bright + 8 dark
- Add 3 known mismatches (poppin_party "Yes! BanG_Dream!", hello_happy_world "Happy! Happier! Happiest!" x2)
- Join with full_catalog_songs.csv to get tag, band, song
- Save to out/pilot_song_list.csv
"""
import pandas as pd
from config import GROUND_TRUTH_LABELS, FULL_CATALOG, OUT_DIR

def main():
    # Load labeled data
    labels_df = pd.read_csv(GROUND_TRUTH_LABELS)
    full_catalog_df = pd.read_csv(FULL_CATALOG)

    # Filter to brightness dimension
    brightness_df = labels_df[labels_df["dimension"] == "brightness"].copy()
    print(f"Total brightness labels: {len(brightness_df)}")

    # Split by label
    bright_df = brightness_df[brightness_df["label"] == "bright"]
    dark_df = brightness_df[brightness_df["label"] == "dark"]

    print(f"Bright songs: {len(bright_df)}")
    print(f"Dark songs: {len(dark_df)}")

    # Collect 16-song baseline
    pilot_16 = pd.concat([bright_df, dark_df], ignore_index=True)
    pilot_16["label"] = pilot_16["label"].str.capitalize()  # bright -> Bright, dark -> Dark

    # Known mismatches (DESIGN.md §0, §2)
    # DESIGN.md specifies these by mode_score PERCENTILE (0.04 / 0.24 / 0.39), not by title
    # guess — "hello_happy_world `Happy! Happier! Happiest!`류 2곡" describes the *theme*
    # (happy-titled songs), but the actual identifying criterion is the percentile value.
    # Verified against data/songs_master.csv (mode_score ranked pct across all 661 songs):
    #   - poppin_party   "Yes! BanG_Dream!"                idx=375  mode_pct=0.0424 (~0.04) ✓
    #   - hello_happy_world "にこ×にこ=ハイパースマイルパワー！" idx=111  mode_pct=0.2405 (~0.24) ✓
    #   - hello_happy_world "えがお･シング･あ･ソング"        idx=109  mode_pct=0.3903 (~0.39) ✓
    # (An earlier draft picked "Happy! Happier! Happiest!" / "ハピネスっ！ハピィーマジカルっ♪"
    # by title-theme guess alone — those sit at mode_pct 0.96/0.95, i.e. already near the top
    # of mode_score, so mode_score would NOT mis-rate them as dark. That is the opposite of
    # a "mismatch" and was corrected here.)

    mismatch_exact = [
        {"band": "poppin_party", "song": "Yes! BanG_Dream!"},
        {"band": "hello_happy_world", "song": "にこ×にこ=ハイパースマイルパワー！"},
        {"band": "hello_happy_world", "song": "えがお･シング･あ･ソング"},
    ]

    # Find tags for mismatches
    mismatches = []
    for ms in mismatch_exact:
        matching_rows = full_catalog_df[
            (full_catalog_df["band"] == ms["band"]) & (full_catalog_df["song"] == ms["song"])
        ]
        if len(matching_rows) > 0:
            row = matching_rows.iloc[0]
            mismatches.append({
                "tag": row["tag"],
                "band": row["band"],
                "song": row["song"],
                "label": "mismatch_known"
            })
        else:
            print(f"Warning: Could not find mismatch {ms['band']} / {ms['song']}")

    if len(mismatches) < 3:
        print(f"Warning: Only found {len(mismatches)} mismatches (expected 3)")
        print("Available hello_happy_world brightness=bright songs:")
        hhw_bright = bright_df[bright_df["band"] == "hello_happy_world"]
        print(hhw_bright[["band", "song"]])

    mismatches_df = pd.DataFrame(mismatches)

    # Combine all 19 songs
    pilot_19_list = []

    # Add 16 labeled songs
    for _, row in pilot_16.iterrows():
        tag = full_catalog_df[
            (full_catalog_df["band"] == row["band"]) & (full_catalog_df["song"] == row["song"])
        ]["tag"].values
        if len(tag) > 0:
            pilot_19_list.append({
                "tag": tag[0],
                "band": row["band"],
                "song": row["song"],
                "label": row["label"]
            })

    # Add 3 mismatches
    for _, row in mismatches_df.iterrows():
        pilot_19_list.append({
            "tag": row["tag"],
            "band": row["band"],
            "song": row["song"],
            "label": row["label"]
        })

    pilot_19_df = pd.DataFrame(pilot_19_list)

    # Save
    output_path = OUT_DIR / "pilot_song_list.csv"
    pilot_19_df.to_csv(output_path, index=False)
    print(f"\nSaved {len(pilot_19_df)} songs to {output_path}")
    print(pilot_19_df.to_string())

if __name__ == "__main__":
    main()
