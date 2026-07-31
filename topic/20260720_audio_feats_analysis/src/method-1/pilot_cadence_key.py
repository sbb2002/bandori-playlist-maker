#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pilot: Cadence-based disambiguation for top-2 key candidates.
Tests whether chord progression cadence analysis can distinguish between
closely-related keys (e.g., A minor vs G major).

Processes 17 songs from morfonica band for which K-S method returns Amin
but suspected ground truth may differ.
"""

import sys
import io
import time
from pathlib import Path
from collections import Counter
import numpy as np
import pandas as pd
import librosa
from scipy.spatial.distance import cosine

# Fix Windows console encoding for unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add method-1 directory to path for config import
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    AUDIO_DIR, OUT_DIR, PITCH_CLASSES, ALL_CHORD_TEMPLATES, KS_PROFILES
)

# 17 pilot songs (all with est_key=Amin that need disambiguation)
PILOT_SONGS = [
    ("morfonica__182", "flame of hope"),
    ("morfonica__191", "誓いのWingbeat"),
    ("morfonica__197", "両翼のBrilliance"),
    ("morfonica__202", "Angel's Ladder"),
    ("morfonica__204", "Tempest"),
    ("morfonica__208", "esora no clover"),
    ("morfonica__210", "Feathered Dreams"),
    ("morfonica__215", "Resonant Strings"),
    ("morfonica__220", "again (Cover)"),
    ("morfonica__221", "輪舞-revolution (Cover)"),
    ("morfonica__223", "祝福 (Cover)"),
    ("morfonica__224", "Overdose (Cover)"),
    ("morfonica__226", "chAngE (Cover)"),
    ("morfonica__228", "Nameless Story (Cover)"),
    ("morfonica__229", "青空のラプソディ (Cover)"),
    ("morfonica__230", "Nevereverland (Cover)"),
    ("morfonica__234", "アゲハ蝶 (Cover)"),
]

# Ground truth (4 songs with verified keys from tunebat.com/Spotify)
GROUND_TRUTH = {
    "morfonica__182": "Gmaj",     # flame of hope
    "morfonica__191": "Amin",     # 誓いのWingbeat
    "morfonica__202": "Bbmaj",    # Angel's Ladder
    "morfonica__221": "Amin",     # 輪舞-revolution
}

OUTPUT_CSV = OUT_DIR / "pilot_cadence_key_17.csv"
REPORT_MD = Path(__file__).parent.parent.parent / "report" / "08-cadence-key-disambiguation-pilot.md"


def estimate_key_top2(chroma, beats):
    """
    Estimate top-2 keys using beat-aligned chroma and KS profiles.
    Returns: [(best_key, best_corr), (second_key, second_corr)]
    """
    if beats is None or len(beats) == 0:
        return [("unknown", 0.0), ("unknown", 0.0)]

    # Average chroma at each beat
    beat_chroma = []
    for beat_idx in beats:
        beat_idx_int = int(np.clip(beat_idx, 0, chroma.shape[1] - 1))
        beat_chroma.append(chroma[:, beat_idx_int])

    if not beat_chroma:
        return [("unknown", 0.0), ("unknown", 0.0)]

    avg_chroma = np.mean(beat_chroma, axis=0)
    avg_chroma = avg_chroma / (np.sum(avg_chroma) + 1e-9)

    # Compute correlations with all 24 profiles
    scores = {}
    for key_name, ks_profile in KS_PROFILES.items():
        corr_result = np.corrcoef(avg_chroma, ks_profile)[0, 1]
        if np.isnan(corr_result):
            corr = 0.0
        else:
            corr = corr_result
        scores[key_name] = corr

    # Sort by correlation (descending) and return top 2
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(sorted_scores[0][0], float(sorted_scores[0][1])),
            (sorted_scores[1][0], float(sorted_scores[1][1]))]


def extract_beat_chords(y, sr, beats):
    """
    Extract chord sequence at each beat position.
    Returns: list of chord names ["Cmaj", "Amin", ...]
    """
    chroma_cqt = librosa.feature.chroma_cqt(y=y, sr=sr)
    beat_chords = []

    for beat_idx in beats:
        beat_idx_int = int(np.clip(beat_idx, 0, chroma_cqt.shape[1] - 1))
        beat_chroma = chroma_cqt[:, beat_idx_int]
        beat_chroma = beat_chroma / (np.sum(beat_chroma) + 1e-9)

        # Find best matching chord
        best_chord = "Cmaj"
        best_sim = -2.0
        for chord_name, chord_template in ALL_CHORD_TEMPLATES.items():
            sim = 1.0 - cosine(beat_chroma, chord_template)
            if sim > best_sim:
                best_sim = sim
                best_chord = chord_name

        beat_chords.append(best_chord)

    return beat_chords


def parse_chord(chord_name):
    """
    Parse chord name to (root_idx, quality).
    E.g., "Cmaj" -> (0, "maj"), "A#min" -> (10, "min")
    Returns: (root_idx: int, quality: str) or (None, None) if parse error
    """
    if "maj" in chord_name:
        root_str = chord_name[:-3]
        quality = "maj"
    elif "min" in chord_name:
        root_str = chord_name[:-3]
        quality = "min"
    else:
        return None, None

    try:
        root_idx = PITCH_CLASSES.index(root_str)
        return root_idx, quality
    except ValueError:
        return None, None


def score_cadence(beat_chords, key_name):
    """
    Score a candidate key based on chord progression analysis.
    Looks for:
      1. Final chord matching tonic triad (+3 points)
      2. V→I progressions (dominant to tonic cadence, +1 point each)
    Returns: (final_chord_score, vi_count)
    """
    if not beat_chords:
        return 0, 0

    # Parse key to get tonic root
    root_str = key_name[:-3]  # Remove "maj" or "min"
    try:
        tonic_root_idx = PITCH_CLASSES.index(root_str)
    except ValueError:
        return 0, 0

    is_major = "maj" in key_name
    tonic_quality = "maj" if is_major else "min"

    # Score 1: Final chord (last 4 beats, use most frequent)
    final_chord_score = 0
    if len(beat_chords) >= 1:
        last_n = min(4, len(beat_chords))
        final_chords = beat_chords[-last_n:]
        most_common_final = Counter(final_chords).most_common(1)[0][0]

        final_root, final_quality = parse_chord(most_common_final)
        if final_root == tonic_root_idx and final_quality == tonic_quality:
            final_chord_score = 3

    # Score 2: V→I progressions (dominant to tonic cadences)
    vi_count = 0
    for i in range(len(beat_chords) - 1):
        prev_chord = beat_chords[i]
        next_chord = beat_chords[i + 1]

        prev_root, prev_quality = parse_chord(prev_chord)
        next_root, next_quality = parse_chord(next_chord)

        if prev_root is None or next_root is None:
            continue

        # Dominant is 7 semitones above tonic (perfect 5th)
        # For major key: V is major, for minor key: V can be major (natural) or minor (harmonic)
        dominant_root_idx = (tonic_root_idx + 7) % 12

        # Check if this is V→I progression
        if prev_root == dominant_root_idx and prev_quality == "maj" and \
           next_root == tonic_root_idx and next_quality == tonic_quality:
            vi_count += 1

    return final_chord_score, vi_count


def process_song(tag, song_name):
    """
    Process a single song and return results dict.
    Returns: dict with all key estimation and cadence analysis, or None if error.
    """
    audio_path = AUDIO_DIR / f"{tag}.wav"

    if not audio_path.exists():
        print(f"  WARNING: Audio file not found at {audio_path}")
        return None

    try:
        # Load audio
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)

        # Extract chroma and beat tracking
        chroma_cqt = librosa.feature.chroma_cqt(y=y, sr=sr)
        onset_envelope = librosa.onset.onset_strength(y=y, sr=sr)
        _, beats = librosa.beat.beat_track(onset_envelope=onset_envelope, sr=sr)

        # Estimate top-2 keys
        top2_keys = estimate_key_top2(chroma_cqt, beats)
        best_key, best_corr = top2_keys[0]
        second_key, second_corr = top2_keys[1]

        # Extract beat chord sequence
        beat_chords = extract_beat_chords(y, sr, beats)

        # Score both candidates
        best_final_score, best_vi_count = score_cadence(beat_chords, best_key)
        second_final_score, second_vi_count = score_cadence(beat_chords, second_key)

        # Calculate final cadence scores
        best_cadence_score = best_final_score + best_vi_count
        second_cadence_score = second_final_score + second_vi_count

        # Decide based on cadence (keep K-S best_key if tie)
        if second_cadence_score > best_cadence_score:
            cadence_pick = second_key
        else:
            cadence_pick = best_key

        # Check ground truth if available
        ground_truth = GROUND_TRUTH.get(tag, None)
        matches_gt = None
        if ground_truth:
            matches_gt = (cadence_pick == ground_truth)

        result = {
            "tag": tag,
            "song": song_name,
            "ks_best_key": best_key,
            "ks_best_corr": best_corr,
            "ks_second_key": second_key,
            "ks_second_corr": second_corr,
            "cadence_final_chord_score_best": best_final_score,
            "cadence_final_chord_score_second": second_final_score,
            "cadence_vi_count_best": best_vi_count,
            "cadence_vi_count_second": second_vi_count,
            "cadence_pick": cadence_pick,
            "ground_truth": ground_truth,
            "matches_ground_truth": matches_gt,
        }

        return result

    except Exception as e:
        print(f"  ERROR processing {tag}: {str(e)}")
        return None


def main():
    start_time = time.time()

    print("=" * 70)
    print("PILOT: Cadence-based Key Disambiguation (17 songs)")
    print("=" * 70)

    # Verify audio directory
    print(f"\nAUDIO_DIR: {AUDIO_DIR}")
    print(f"OUT_DIR:   {OUT_DIR}")

    # Process each pilot song
    results = []
    for idx, (tag, song_name) in enumerate(PILOT_SONGS, 1):
        print(f"\n[{idx:2d}/17] Processing {tag} ({song_name})...")
        result = process_song(tag, song_name)

        if result:
            results.append(result)
            print(f"       KS best: {result['ks_best_key']} ({result['ks_best_corr']:.3f})")
            print(f"       KS 2nd:  {result['ks_second_key']} ({result['ks_second_corr']:.3f})")
            print(f"       Cadence pick: {result['cadence_pick']}")
            if result['ground_truth']:
                status = "OK" if result['matches_ground_truth'] else "FAIL"
                print(f"       [{status}] Ground truth: {result['ground_truth']} "
                      f"(match={result['matches_ground_truth']})")

    # Build output dataframe
    df = pd.DataFrame(results)

    # Save to CSV
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"\n[OK] Saved {len(df)} results to {OUTPUT_CSV}")

    # Generate markdown report
    generate_report(df)

    elapsed = time.time() - start_time
    print(f"\nTotal time: {elapsed:.1f} seconds")


def generate_report(df):
    """
    Generate markdown report summarizing cadence-key disambiguation results.
    """
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)

    # Count changes from K-S best to cadence pick
    n_changed = (df["ks_best_key"] != df["cadence_pick"]).sum()

    # Evaluate ground truth accuracy
    gt_mask = df["ground_truth"].notna()
    n_gt_songs = gt_mask.sum()
    n_gt_correct = (df.loc[gt_mask, "matches_ground_truth"] == True).sum()

    # Find songs where cadence changed the pick
    changed_songs = df[df["ks_best_key"] != df["cadence_pick"]]

    # Build report
    report = f"""# Report 08: Cadence-based Key Disambiguation Pilot

## Objective
Test whether chord progression cadence analysis can disambiguate between the top-2 K-S key candidates.
Background: Krumhansl-Schmuckler correlation cannot distinguish closely-related keys (e.g., A minor ↔ G major,
differing by only 1 pitch in the diatonic scale).

## Hypothesis
Two key candidates related by a perfect 5th (differing by one accidental pitch) can be distinguished by analyzing:
1. **Final chord**: Does the song end on the tonic triad of candidate 1 or 2?
2. **V→I cadences**: Are dominant→tonic progressions more prevalent in candidate 1 or 2?

## Dataset
- **17 songs** from *morfonica* band (K-S estimated key = A minor)
- **4 songs with ground truth** (verified via tunebat.com / Spotify)
- **13 songs unverified** (ground truth unknown)

## Methodology
For each song and each K-S candidate (best and 2nd):
1. Extract beat-aligned chord sequence (cosine similarity vs. triad templates)
2. **Final chord score** (+3): Majority chord in last 4 beats matches tonic triad
3. **V→I cadence count** (+1 each): Count of "dominant major → tonic" transitions
4. **Cadence pick**: Candidate with higher combined score (ties favor K-S best)

## Results

### Summary Statistics
- **Total songs**: {len(df)}
- **Songs where cadence changed the pick**: {n_changed} ({100*n_changed/len(df):.1f}%)
- **Ground truth accuracy (before)**: 2/4 (50%) — Wingbeat, 輪舞-revolution correct; flame of hope, Angel's Ladder wrong
- **Ground truth accuracy (after)**: {n_gt_correct}/{n_gt_songs} ({100*n_gt_correct/max(1,n_gt_songs):.1f}%)

### Songs with Changed Decisions
{_format_changed_songs_section(changed_songs) if len(changed_songs) > 0 else "None — all songs kept K-S best decision."}

### Ground Truth Evaluation (4 songs)
{_format_ground_truth_section(df)}

## Conclusion
{_generate_conclusion(n_changed, n_gt_correct, n_gt_songs, len(df))}

## Next Steps
1. **Expand ground truth**: Manually verify 5-10 more songs from changed decisions
2. **Refine V→I detection**: Consider harmonic minor V (dominant seventh) patterns
3. **Full evaluation**: If accuracy improves on ground truth, extend to all 661 songs
"""

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[OK] Generated report: {REPORT_MD}")


def _format_changed_songs_section(changed_df):
    """Format section listing songs where cadence changed the decision."""
    lines = []
    for _, row in changed_df.iterrows():
        gt_status = ""
        if row["ground_truth"]:
            match_symbol = "OK" if row["matches_ground_truth"] else "FAIL"
            gt_status = f" | Ground: {row['ground_truth']} [{match_symbol}]"

        line = (
            f"- **{row['tag']}** ({row['song']}) "
            f"K-S: {row['ks_best_key']} -> Cadence: {row['cadence_pick']}"
            f"{gt_status}"
        )
        lines.append(line)

    return "\n".join(lines)


def _format_ground_truth_section(df):
    """Format ground truth evaluation section."""
    gt_rows = df[df["ground_truth"].notna()]
    lines = []
    for _, row in gt_rows.iterrows():
        match_symbol = "OK" if row["matches_ground_truth"] else "FAIL"
        line = (
            f"- [{match_symbol}] **{row['tag']}** ({row['song']}): "
            f"Ground={row['ground_truth']}, "
            f"K-S best={row['ks_best_key']}, "
            f"Cadence pick={row['cadence_pick']}"
        )
        lines.append(line)
    return "\n".join(lines)


def _generate_conclusion(n_changed, n_gt_correct, n_gt_songs, total_songs):
    """Generate conclusion text based on results."""
    if n_gt_correct > 2:  # Improvement over baseline 2/4
        return (
            f"Cadence analysis shows **promise**: {n_gt_correct}/{n_gt_songs} ground truth songs now correct "
            f"(vs. 2/4 baseline). {n_changed} songs changed decisions. "
            f"Recommend expanding ground truth pool and refining V→I detection before full rollout."
        )
    elif n_gt_correct == 2:
        return (
            f"Cadence analysis is **neutral**: {n_gt_correct}/{n_gt_songs} ground truth songs correct (same as baseline). "
            f"{n_changed} songs changed decisions. May need to refine scoring or examine additional features. "
            f"Recommend blind listening evaluation of changed decisions before proceeding."
        )
    else:
        return (
            f"Cadence analysis shows **no improvement**: {n_gt_correct}/{n_gt_songs} ground truth songs correct "
            f"(vs. 2/4 baseline). {n_changed} songs changed decisions but accuracy declined. "
            f"Consider alternative approaches (e.g., temporal cadence patterns, tonic harmony emphasis)."
        )


if __name__ == "__main__":
    main()
