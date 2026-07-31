"""Extract chords from no_vocals.wav using chroma + beat tracking + template matching.

DESIGN.md §3:
1. librosa.load(no_vocals.wav, sr=22050) → chroma_cqt
2. beat_track() for beat boundaries
3. Average chroma per beat
4. 24-template cosine similarity matching (major + minor triads)
5. Merge adjacent identical chords
6. Krumhansl-Schmuckler global key estimation
Output: out/chord_sequences.csv + out/chord_progress.json (idempotent)
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import librosa
from scipy.spatial.distance import cosine

from config import (
    STEMS_BASE,
    ALL_CHORD_TEMPLATES,
    KS_PROFILES,
    PITCH_CLASSES,
    OUT_DIR,
)

# Suppress librosa/scipy warnings
warnings.filterwarnings("ignore")


def load_progress():
    """Load idempotent progress tracker (chord_progress.json)."""
    progress_file = OUT_DIR / "chord_progress.json"
    if progress_file.exists():
        with open(progress_file, "r") as f:
            return json.load(f)
    return {"processed": {}, "total": 0}


def save_progress(progress):
    """Save progress to chord_progress.json."""
    progress_file = OUT_DIR / "chord_progress.json"
    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)


def extract_chords_from_song(tag: str, audio_path: Path) -> dict:
    """
    Extract chord sequence from audio file.

    DESIGN.md §3 procedure:
    1. Load audio, extract chroma_cqt
    2. Beat track
    3. Average chroma per beat
    4. Template match (24 templates) → chord + confidence
    5. Merge adjacent identical chords
    6. Estimate global key via K-S profile

    Args:
        tag: Song identifier
        audio_path: Path to no_vocals.wav

    Returns:
        Dict with:
        - chords: List of (beat_idx, chord_root, chord_quality, confidence)
        - est_key: Estimated global key (e.g., "Cmaj")
        - bpm: Estimated beats per minute
    """
    # Load audio
    y, sr = librosa.load(str(audio_path), sr=22050)

    # Extract chroma (12 pitch classes per frame)
    # chroma_cqt is tuning-robust, suitable for guitar-heavy material
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)  # (12, n_frames)

    # Beat track to get beat times (in frames)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env)
    tempo = float(np.asarray(tempo).reshape(-1)[0])  # librosa 0.11: tempo is a 1-element ndarray, not a scalar

    # beats is in frame indices; convert to sample indices if needed
    # Actually, beat_track returns frame indices relative to the onset_strength
    # We need beat times in frames for alignment with chroma

    # Average chroma by beat: for each beat interval, average the chroma
    beat_chroma = []
    for i in range(len(beats) - 1):
        start_frame = beats[i]
        end_frame = beats[i + 1]
        if end_frame > start_frame:
            avg_chroma = np.mean(chroma[:, start_frame:end_frame], axis=1)
            beat_chroma.append(avg_chroma)

    # Ensure last beat is included
    if len(beats) > 0:
        start_frame = beats[-1]
        if start_frame < chroma.shape[1]:
            avg_chroma = np.mean(chroma[:, start_frame:], axis=1)
            beat_chroma.append(avg_chroma)

    beat_chroma = np.array(beat_chroma)  # (n_beats, 12)

    if len(beat_chroma) == 0:
        raise ValueError(f"{tag}: No beats detected")

    # Template matching: for each beat, find best matching chord template
    chord_sequence = []
    for beat_idx, chroma_vec in enumerate(beat_chroma):
        # Normalize chroma
        chroma_norm = chroma_vec / (np.linalg.norm(chroma_vec) + 1e-6)

        # Compute cosine similarity with each template
        best_chord = None
        best_sim = -np.inf
        for chord_name, template in ALL_CHORD_TEMPLATES.items():
            template_norm = template / (np.linalg.norm(template) + 1e-6)
            # Cosine similarity: dot product of normalized vectors
            sim = np.dot(chroma_norm, template_norm)
            if sim > best_sim:
                best_sim = sim
                best_chord = chord_name

        if best_chord is None:
            best_chord = "Cmaj"
            best_sim = 0.0

        chord_root, chord_quality = best_chord[:-3], best_chord[-3:]

        chord_sequence.append({
            "beat_idx": beat_idx,
            "chord": best_chord,
            "root": chord_root,
            "quality": chord_quality,
            "confidence": float(max(0.0, best_sim)),  # Clip to [0, inf)
        })

    # Merge adjacent identical chords
    merged_sequence = []
    if chord_sequence:
        current_chord = chord_sequence[0]["chord"]
        start_beat = 0

        for i in range(1, len(chord_sequence)):
            if chord_sequence[i]["chord"] != current_chord:
                # End of current chord segment
                duration = i - start_beat
                merged_sequence.append({
                    "chord": current_chord,
                    "start_beat": start_beat,
                    "duration_beats": duration,
                })
                current_chord = chord_sequence[i]["chord"]
                start_beat = i

        # Finalize last segment
        duration = len(chord_sequence) - start_beat
        merged_sequence.append({
            "chord": current_chord,
            "start_beat": start_beat,
            "duration_beats": duration,
        })

    # Global key estimation via K-S profile
    # Compute mean chroma across entire song
    mean_chroma = np.mean(beat_chroma, axis=0)

    # BUGFIX (code review): the standard Krumhansl-Schmuckler key-finding
    # algorithm scores each of the 24 key profiles by the *Pearson
    # correlation coefficient* with the chroma vector (DESIGN.md §3.5: "곡
    # 전체 평균 크로마의 상관으로 추정"). The original code instead computed
    # a plain dot product of an L2-normalized chroma vector against
    # sum-normalized (probability-like) profiles — not a correlation at all
    # (no mean-centering), which changes the ranking versus true K-S. Fixed
    # to use np.corrcoef, matching the textbook algorithm.
    best_key = "Cmaj"
    best_corr = -np.inf
    for key_name, ks_profile in KS_PROFILES.items():
        corr = np.corrcoef(mean_chroma, ks_profile)[0, 1]
        if np.isnan(corr):
            corr = -np.inf
        if corr > best_corr:
            best_corr = corr
            best_key = key_name

    return {
        "beat_chroma_detailed": chord_sequence,
        "chord_sequence_merged": merged_sequence,
        "est_key": best_key,
        "est_key_confidence": float(best_corr),
        "tempo_bpm": float(tempo),
        "n_beats": len(beat_chroma),
    }


def main():
    # Load pilot song list
    pilot_path = OUT_DIR / "pilot_song_list.csv"
    if not pilot_path.exists():
        raise FileNotFoundError(
            f"Pilot song list not found. Run 01_select_pilot_songs.py first."
        )

    pilot_df = pd.read_csv(pilot_path)
    print(f"Processing {len(pilot_df)} pilot songs for chord extraction...")

    # Load progress
    progress = load_progress()

    # Output rows
    output_rows = []

    for idx, row in pilot_df.iterrows():
        tag = row["tag"]
        print(f"[{idx + 1}/{len(pilot_df)}] {tag}...", end=" ", flush=True)

        # Skip if already processed
        if tag in progress["processed"]:
            print("(cached)")
            # Load cached results
            cached_chords = progress["processed"][tag]["chord_sequences"]
            for chord_row in cached_chords:
                output_rows.append(chord_row)
            continue

        # Audio path
        audio_path = STEMS_BASE / tag / "no_vocals.wav"
        if not audio_path.exists():
            print(f"WARNING: Audio not found at {audio_path}")
            continue

        try:
            # Extract chords
            result = extract_chords_from_song(tag, audio_path)

            # Store beat-level chord sequence
            beat_level = result["beat_chroma_detailed"]
            for chord_info in beat_level:
                output_rows.append({
                    "tag": tag,
                    "beat_idx": chord_info["beat_idx"],
                    "chord_root": chord_info["root"],
                    "chord_quality": chord_info["quality"],
                    "confidence": chord_info["confidence"],
                })

            # Cache in progress
            progress["processed"][tag] = {
                "est_key": result["est_key"],
                "est_key_confidence": result["est_key_confidence"],
                "tempo_bpm": result["tempo_bpm"],
                "n_beats": result["n_beats"],
                "chord_sequences": [
                    {
                        "tag": tag,
                        "beat_idx": chord_info["beat_idx"],
                        "chord_root": chord_info["root"],
                        "chord_quality": chord_info["quality"],
                        "confidence": chord_info["confidence"],
                    }
                    for chord_info in beat_level
                ],
            }
            progress["total"] += 1
            save_progress(progress)

            print(f"OK ({result['n_beats']} beats, key={result['est_key']})")

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    # Save chord sequences
    if output_rows:
        output_df = pd.DataFrame(output_rows)
        output_path = OUT_DIR / "chord_sequences.csv"
        output_df.to_csv(output_path, index=False)
        print(f"\nSaved {len(output_df)} chord records to {output_path}")
    else:
        print("No chord sequences generated")


if __name__ == "__main__":
    main()
