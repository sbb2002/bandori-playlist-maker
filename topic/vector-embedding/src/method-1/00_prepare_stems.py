"""Prepare vocal stems for SAMPLE_TAGS songs using demucs (two-stems).

Usage:
    python 00_prepare_stems.py           # Process all SAMPLE_TAGS
    python 00_prepare_stems.py --limit 1 # Process only first song (smoke test)
"""
import argparse
import subprocess
import sys
from pathlib import Path

import config

SCRIPT_DIR = Path(__file__).parent
DEMUCS_RUNNER = SCRIPT_DIR / "_demucs_run.py"


def prepare_stems(limit=None):
    """Separate vocals from songs in SAMPLE_TAGS.

    Args:
        limit: If set, process only the first N songs (for smoke testing).
    """
    config.STEMS_DIR.mkdir(parents=True, exist_ok=True)
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)

    tags = config.SAMPLE_TAGS
    if limit:
        tags = tags[:limit]

    total = len(tags)
    processed = 0
    skipped = 0

    for i, tag in enumerate(tags, 1):
        vocal_path = config.STEMS_DIR / tag / "vocals.wav"

        # Already processed?
        if vocal_path.exists():
            print(f"[{i}/{total}] {tag} - already processed (skip)")
            skipped += 1
            continue

        audio_path = Path(config.AUDIO_DIR) / f"{tag}.wav"
        if not audio_path.exists():
            print(f"[{i}/{total}] {tag} - audio not found at {audio_path} (skip)")
            skipped += 1
            continue

        print(f"[{i}/{total}] {tag} - separating vocals...")

        # Demucs output goes to work/htdemucs_temp/<tag>/vocals.wav
        temp_out = config.WORK_DIR / "htdemucs_temp"
        temp_out.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(DEMUCS_RUNNER),
            "-n", "htdemucs",
            "--two-stems", "vocals",
            "-o", str(temp_out),
            str(audio_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if result.returncode != 0:
                print(f"  ERROR: demucs failed")
                print(f"  stdout: {result.stdout}")
                print(f"  stderr: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, cmd)
        except Exception as e:
            print(f"  ERROR: {e}")
            raise

        # demucs writes to <out>/<model_name>/<input_stem>/vocals.wav
        demucs_out = temp_out / "htdemucs" / tag / "vocals.wav"
        if not demucs_out.exists():
            raise FileNotFoundError(f"Demucs output not found: {demucs_out}")

        # Create target directory and move file
        vocal_path.parent.mkdir(parents=True, exist_ok=True)
        demucs_out.rename(vocal_path)

        print(f"  → saved to {vocal_path}")
        processed += 1

    print(f"\nDone: {processed} processed, {skipped} skipped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare vocal stems using demucs")
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N songs")
    args = parser.parse_args()

    prepare_stems(limit=args.limit)
