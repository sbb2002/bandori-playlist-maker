#!/usr/bin/env python3
"""
Extract audio features (MFCC, LUFS, chord progression) for 661 songs.
Idempotent processing with progress tracking.
"""

import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import librosa
import pyloudnorm
from scipy.spatial.distance import cosine

from config import (
    PROJECT_ROOT, AUDIO_DIR, FULL_CATALOG, OUT_DIR,
    PITCH_CLASSES, ALL_CHORD_TEMPLATES, KS_PROFILES, DIATONIC_POOLS
)

PROGRESS_FILE = OUT_DIR / "progress.json"
OUTPUT_CSV = OUT_DIR / "audio_feats.csv"


def load_progress():
    """Load progress tracking file."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(progress):
    """Save progress tracking file."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def extract_mfcc(y, sr):
    """
    Extract MFCC features.
    Returns: dict with mfcc_*_mean and mfcc_*_std keys (13 MFCCs, 26 total features).
    """
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_means = np.mean(mfcc, axis=1)
    mfcc_stds = np.std(mfcc, axis=1)

    features = {}
    for i in range(13):
        features[f"mfcc_{i+1}_mean"] = float(mfcc_means[i])
        features[f"mfcc_{i+1}_std"] = float(mfcc_stds[i])
    return features


def extract_lufs(y, sr):
    """
    Extract LUFS (Loudness Units relative to Full Scale).
    Returns: float LUFS value.
    """
    meter = pyloudnorm.Meter(sr)
    loudness = meter.integrated_loudness(y.astype(np.float64))
    return float(loudness)


def merge_existing_features(new_df):
    """
    Merge new features with existing features from data/ folder.
    Uses idx (parsed from tag) as the join key to avoid 1:N matches on duplicate song titles.
    Returns: merged DataFrame.
    """
    result_df = new_df.copy()

    # Parse idx from tag (format: band__XXX where XXX is idx)
    result_df["idx"] = result_df["tag"].str.split("__").str[-1].astype(int)

    # Paths to existing feature CSV files
    data_dir = PROJECT_ROOT / "data"
    songs_master_path = data_dir / "songs_master.csv"
    full_audio_features_path = data_dir / "full_audio_features.csv"
    song_features_with_proxies_path = data_dir / "song_features_with_proxies.csv"

    # Load and merge songs_master.csv via idx
    if songs_master_path.exists():
        print(f"Merging {songs_master_path.name} (via idx)...")
        songs_master = pd.read_csv(songs_master_path)
        before_len = len(result_df)
        result_df = result_df.merge(songs_master, on="idx", how="left", suffixes=("", "_master"))
        after_len = len(result_df)
        print(f"  Merged {songs_master_path.name}: {before_len} rows -> {after_len} rows")
    else:
        print(f"WARNING: {songs_master_path} not found")

    # Load and merge full_audio_features.csv via idx
    if full_audio_features_path.exists():
        print(f"Merging {full_audio_features_path.name} (via idx)...")
        full_audio_features = pd.read_csv(full_audio_features_path)
        before_len = len(result_df)
        result_df = result_df.merge(full_audio_features, on="idx", how="left", suffixes=("", "_audio"))
        after_len = len(result_df)
        print(f"  Merged {full_audio_features_path.name}: {before_len} rows -> {after_len} rows")
    else:
        print(f"WARNING: {full_audio_features_path} not found")

    # Load and merge song_features_with_proxies.csv via idx
    if song_features_with_proxies_path.exists():
        print(f"Merging {song_features_with_proxies_path.name} (via idx)...")
        song_features_with_proxies = pd.read_csv(song_features_with_proxies_path)
        before_len = len(result_df)
        result_df = result_df.merge(song_features_with_proxies, on="idx", how="left", suffixes=("", "_proxies"))
        after_len = len(result_df)
        print(f"  Merged {song_features_with_proxies_path.name}: {before_len} rows -> {after_len} rows")
    else:
        print(f"WARNING: {song_features_with_proxies_path} not found")

    print(f"Final shape: {len(result_df)} rows x {len(result_df.columns)} columns")
    return result_df


def estimate_key(chroma, beats):
    """
    Estimate the key using beat-aligned chroma and KS profiles.
    Returns: (est_key_str, correlation_score)
    """
    if beats is None or len(beats) == 0:
        return "unknown", 0.0

    # Average chroma at each beat
    beat_chroma = []
    for beat_idx in beats:
        beat_idx_int = int(np.clip(beat_idx, 0, chroma.shape[1] - 1))
        beat_chroma.append(chroma[:, beat_idx_int])

    if not beat_chroma:
        return "unknown", 0.0

    avg_chroma = np.mean(beat_chroma, axis=0)
    avg_chroma = avg_chroma / (np.sum(avg_chroma) + 1e-9)

    best_key = "Cmaj"
    best_corr = -2.0
    for key_name, ks_profile in KS_PROFILES.items():
        # Handle NaN from corrcoef
        corr_result = np.corrcoef(avg_chroma, ks_profile)[0, 1]
        if np.isnan(corr_result):
            corr = 0.0
        else:
            corr = corr_result
        if corr > best_corr:
            best_corr = corr
            best_key = key_name

    return best_key, float(best_corr)


def extract_chord_features(y, sr, tempo_bpm):
    """
    Extract chord progression derived features.
    Returns: dict with tempo_bpm, n_beats, est_key, pct_major, chord_change_rate, borrowed_chord_rate
    """
    # Compute chroma and beat tracking
    chroma_cqt = librosa.feature.chroma_cqt(y=y, sr=sr)

    # Beat tracking
    onset_envelope = librosa.onset.onset_strength(y=y, sr=sr)
    beats = librosa.beat.beat_track(onset_envelope=onset_envelope, sr=sr)[1]

    est_key, _ = estimate_key(chroma_cqt, beats)

    # Match chords at each beat
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

    n_beats = len(beat_chords)

    # Calculate pct_major
    n_major = sum(1 for c in beat_chords if "maj" in c)
    pct_major = float(n_major / max(1, n_beats))

    # Calculate chord_change_rate (chords per minute)
    if n_beats > 0 and tempo_bpm > 0:
        duration_minutes = n_beats / (tempo_bpm / 60.0) / 60.0  # beats -> seconds -> minutes
        chord_changes = sum(1 for i in range(1, len(beat_chords)) if beat_chords[i] != beat_chords[i-1])
        chord_change_rate = float(chord_changes / max(1, duration_minutes))
    else:
        chord_change_rate = 0.0

    # Calculate borrowed_chord_rate
    diatonic_pool = DIATONIC_POOLS.get(est_key, set())
    n_borrowed = 0
    for chord_name in beat_chords:
        # Parse chord name to (root, quality)
        if "maj" in chord_name:
            root_str = chord_name[:-3]
            quality = "maj"
        else:
            root_str = chord_name[:-3]
            quality = "min"

        try:
            root_idx = PITCH_CLASSES.index(root_str)
            if (root_idx, quality) not in diatonic_pool:
                n_borrowed += 1
        except ValueError:
            n_borrowed += 1

    borrowed_chord_rate = float(n_borrowed / max(1, n_beats))

    return {
        "tempo_bpm": float(tempo_bpm),
        "n_beats": int(n_beats),
        "est_key": est_key,
        "pct_major": pct_major,
        "chord_change_rate": chord_change_rate,
        "borrowed_chord_rate": borrowed_chord_rate,
    }


def process_song(tag, band, song, audio_path, progress):
    """
    Process a single song and return features dict.
    Returns: dict with all features or None if error/skip.
    """
    if tag in progress:
        status = progress[tag].get("status", "unknown")
        if status == "success":
            return progress[tag].copy()
        elif status == "missing_audio":
            return None
        elif status == "error":
            return None

    # Check audio file exists
    if not audio_path.exists():
        progress[tag] = {"status": "missing_audio", "tag": tag, "band": band, "song": song}
        return None

    try:
        # Load audio
        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)

        # Extract MFCC
        mfcc_features = extract_mfcc(y, sr)

        # Extract LUFS
        lufs = extract_lufs(y, sr)

        # Extract chord features (includes tempo_bpm estimation)
        onset_envelope = librosa.onset.onset_strength(y=y, sr=sr)
        tempo_bpm, _ = librosa.beat.beat_track(onset_envelope=onset_envelope, sr=sr)
        chord_features = extract_chord_features(y, sr, tempo_bpm)

        # Combine all features
        result = {
            "status": "success",
            "tag": tag,
            "band": band,
            "song": song,
            "lufs": lufs,
            **mfcc_features,
            **chord_features,
        }

        progress[tag] = result
        return result

    except Exception as e:
        progress[tag] = {
            "status": "error",
            "tag": tag,
            "band": band,
            "song": song,
            "message": str(e),
        }
        return None


def main():
    start_time = time.time()

    print("Loading configuration...")
    print(f"FULL_CATALOG path: {FULL_CATALOG}")
    print(f"FULL_CATALOG exists: {FULL_CATALOG.exists()}")

    if not FULL_CATALOG.exists():
        print(f"ERROR: FULL_CATALOG not found at {FULL_CATALOG}")
        return

    print(f"AUDIO_DIR path: {AUDIO_DIR}")
    print(f"AUDIO_DIR exists: {AUDIO_DIR.exists()}")

    # Load catalog
    df = pd.read_csv(FULL_CATALOG)
    print(f"Loaded {len(df)} songs from catalog")

    # Load progress
    progress = load_progress()
    print(f"Resuming from {len(progress)} already-processed songs")

    # Process each song
    results = []
    n_success = 0
    n_skip = 0
    n_error = 0

    for idx, row in df.iterrows():
        tag = row["tag"]
        band = row["band"]
        song = row["song"]
        audio_path = AUDIO_DIR / f"{tag}.wav"

        result = process_song(tag, band, song, audio_path, progress)

        if result is None:
            if tag in progress and progress[tag].get("status") == "missing_audio":
                n_skip += 1
                print(f"[{idx+1}/661] {tag}... SKIP (missing audio)")
            else:
                n_error += 1
                print(f"[{idx+1}/661] {tag}... ERROR")
        else:
            n_success += 1
            results.append(result)
            print(f"[{idx+1}/661] {tag}... OK")

        # Save progress after each song
        save_progress(progress)

    # Build output dataframe
    output_df = pd.DataFrame(results)

    # Merge with existing features from data/ folder
    output_df = merge_existing_features(output_df)

    # Save to CSV
    output_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
    print(f"\nSaved {len(output_df)} results to {OUTPUT_CSV}")

    # Calculate statistics
    elapsed_time = time.time() - start_time
    elapsed_minutes = elapsed_time / 60.0
    avg_time_per_song = elapsed_time / max(1, len(df))

    print(f"\n=== SUMMARY ===")
    print(f"Total songs processed: {len(df)}")
    print(f"Success: {n_success}")
    print(f"Skip (missing audio): {n_skip}")
    print(f"Error: {n_error}")
    print(f"Total elapsed time: {elapsed_time:.1f} seconds ({elapsed_minutes:.1f} minutes)")
    print(f"Average time per song: {avg_time_per_song:.2f} seconds")

    # Show sample errors if any
    if n_error > 0:
        print(f"\n=== SAMPLE ERRORS ===")
        error_count = 0
        for tag, info in progress.items():
            if info.get("status") == "error" and error_count < 5:
                print(f"{tag}: {info.get('message', 'unknown error')}")
                error_count += 1


if __name__ == "__main__":
    main()
