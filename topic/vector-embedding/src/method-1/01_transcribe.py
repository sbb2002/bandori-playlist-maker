"""ASR transcription using faster-whisper.

Reads SAMPLE_TAGS songs, transcribes vocals, saves to work/transcripts and out/transcripts_meta.csv.
"""
from pathlib import Path
import csv
import sys

import pandas as pd
from faster_whisper import WhisperModel

import config

SCRIPT_DIR = Path(__file__).parent


def transcribe_all():
    """Transcribe vocals for SAMPLE_TAGS using faster-whisper."""
    # Setup directories
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    transcripts_dir = config.WORK_DIR / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # Load songs and filter to SAMPLE_TAGS
    df_songs = pd.read_csv(config.SONGS_CSV)
    df_songs = df_songs[df_songs["tag"].isin(config.SAMPLE_TAGS)].reset_index(drop=True)

    if len(df_songs) == 0:
        print(f"ERROR: No songs found in {config.SONGS_CSV} with SAMPLE_TAGS")
        sys.exit(1)

    print(f"Found {len(df_songs)} songs to transcribe")

    # Previous metadata (for cached transcripts on rerun)
    meta_csv_path = config.OUT_DIR / "transcripts_meta.csv"
    prev_meta = {}
    if meta_csv_path.exists():
        prev_df = pd.read_csv(meta_csv_path)
        prev_meta = {r["tag"]: r.to_dict() for _, r in prev_df.iterrows()}

    # Load whisper model
    print(f"Loading WhisperModel: {config.WHISPER_MODEL} (compute: {config.WHISPER_COMPUTE})")
    model = WhisperModel(config.WHISPER_MODEL, compute_type=config.WHISPER_COMPUTE)

    # Transcribe each song
    results = []
    for idx, row in df_songs.iterrows():
        tag = row["tag"]
        band = row["band"]
        song = row["song"]

        transcript_file = transcripts_dir / f"{tag}.txt"

        # Idempotent: skip if already processed
        if transcript_file.exists():
            print(f"[{idx+1}/{len(df_songs)}] {tag} - already transcribed (skip)")
            # Reuse previous metadata row if available; else recompute basic stats
            if tag in prev_meta:
                results.append(prev_meta[tag])
            else:
                text = transcript_file.read_text(encoding="utf-8")
                results.append(_extract_metadata(text, tag, band, song))
            continue

        # Load vocal stem
        vocal_file = config.STEMS_DIR / tag / "vocals.wav"
        if not vocal_file.exists():
            print(f"[{idx+1}/{len(df_songs)}] {tag} - vocal stem not found at {vocal_file}")
            sys.exit(1)

        print(f"[{idx+1}/{len(df_songs)}] {tag} - transcribing...")

        # Whisper parameters (DESIGN §5)
        segments, info = model.transcribe(
            str(vocal_file),
            language=None,  # auto-detect
            vad_filter=True,
            temperature=0.0,
            condition_on_previous_text=False,
            beam_size=5,
        )

        # Collect segments (post-processing)
        texts = []
        logprobs = []
        for segment in segments:
            # Strip each segment
            text = segment.text.strip()
            if text:
                texts.append(text)
                # logprob: average of token logprobs
                if segment.avg_logprob is not None:
                    logprobs.append(segment.avg_logprob)

        # Remove consecutive duplicates
        unique_texts = []
        for text in texts:
            if not unique_texts or unique_texts[-1] != text:
                unique_texts.append(text)

        final_text = "\n".join(unique_texts)

        # Save transcript
        transcript_file.write_text(final_text, encoding="utf-8")
        print(f"  → saved to {transcript_file}")

        # Extract metadata
        meta = {
            "tag": tag,
            "band": band,
            "song": song,
            "detected_lang": info.language if info else None,
            "lang_prob": float(info.language_probability) if info and info.language_probability else None,
            "n_segments": len(texts),  # segments is a consumed generator; count collected texts
            "n_chars": len(final_text),
            "avg_logprob_mean": sum(logprobs) / len(logprobs) if logprobs else None,
        }
        results.append(meta)

    # Save metadata CSV
    meta_csv = config.OUT_DIR / "transcripts_meta.csv"
    df_meta = pd.DataFrame(results)
    df_meta.to_csv(meta_csv, index=False, encoding="utf-8-sig" if False else "utf-8")
    print(f"\nSaved metadata to {meta_csv}")

    # QC checkpoint
    print(
        "\n--- QC CHECKPOINT ---"
        "\nBefore proceeding to step 02, please verify ASR quality:"
        "\n  1. Open 3+ transcripts from work/transcripts/<tag>.txt"
        "\n  2. Listen to the corresponding audio and verify accuracy"
        "\n  3. Check for obvious hallucinations (repeated words/phrases)"
        "\nIf ASR quality is acceptable, proceed to 02_build_texts.py"
    )


def _extract_metadata(text, tag, band, song):
    """Extract metadata from raw transcript text."""
    # For cached files, we need to recompute basic stats
    n_chars = len(text)
    n_segments = text.count("\n") + (1 if text.strip() else 0)
    return {
        "tag": tag,
        "band": band,
        "song": song,
        "detected_lang": None,  # Can't recompute from text alone
        "lang_prob": None,
        "n_segments": n_segments,
        "n_chars": n_chars,
        "avg_logprob_mean": None,
    }


if __name__ == "__main__":
    transcribe_all()
