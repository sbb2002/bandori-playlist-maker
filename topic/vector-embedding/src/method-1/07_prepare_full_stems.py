"""Stage 2 full-catalog prep: demucs vocal separation for all 661 songs.

Mirrors topic/mfcc_analysis/separate_vocals.py's approach (reuses its _demucs_run.py
monkeypatch runner) but writes into this folder's own work/stems_full/ instead of
mfcc_analysis/stems -- that folder's scope is deliberately capped at 30 songs
(README.md), this is vector-embedding's own full-catalog run.

Resume-safe: skips tags whose vocals.wav already exists. Writes out/stage2_full_progress.json
after every song so progress is visible without tailing logs.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import config

SCRIPT_DIR = Path(__file__).parent
MFCC_DIR = SCRIPT_DIR / "../../../mfcc_analysis"
DEMUCS_RUNNER = MFCC_DIR / "_demucs_run.py"
LOCAL_AUDIO_DIR = r"C:\Users\User\Documents\pyworks\bandori-song-sorter\src\content\cluster\audio_full"
STEMS_FULL_DIR = SCRIPT_DIR / "work" / "stems_full"
CATALOG_CSV = SCRIPT_DIR / "full_catalog_songs.csv"
PROGRESS_PATH = config.OUT_DIR / "stage2_full_progress.json"


def save_progress(progress, **fields):
    progress.update(fields)
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    STEMS_FULL_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(CATALOG_CSV)
    total = len(df)
    progress = {
        "step": "demucs_full_catalog",
        "n_total": total,
        "n_done": 0,
        "n_skipped": 0,
        "n_failed": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    save_progress(progress, status="in_progress")

    done, skipped, failed = 0, 0, []
    t0 = time.time()
    for n, row in enumerate(df.itertuples(), 1):
        voc_out = STEMS_FULL_DIR / "htdemucs" / row.tag / "vocals.wav"
        if voc_out.is_file():
            skipped += 1
            continue
        src = os.path.join(LOCAL_AUDIO_DIR, row.tag + ".wav")
        if not os.path.isfile(src):
            failed.append((row.tag, "no source audio"))
            continue

        cmd = [
            sys.executable, str(DEMUCS_RUNNER), "-n", "htdemucs",
            "--two-stems", "vocals", "-o", str(STEMS_FULL_DIR), src,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not voc_out.is_file():
            failed.append((row.tag, proc.stderr[-300:]))
        else:
            done += 1

        if n % 10 == 0 or n == total:
            elapsed = time.time() - t0
            rate = (done + skipped) / elapsed if elapsed > 0 else 0
            eta_sec = (total - n) / rate if rate > 0 else None
            print(f"[{n}/{total}] done={done} skipped={skipped} failed={len(failed)} "
                  f"eta_min={eta_sec/60:.1f}" if eta_sec else f"[{n}/{total}] done={done}")
            save_progress(
                progress, status="in_progress", n_done=done, n_skipped=skipped,
                n_failed=len(failed), n_processed=n,
                eta_min=round(eta_sec / 60, 1) if eta_sec else None,
            )

    save_progress(progress, status="done", n_done=done, n_skipped=skipped, n_failed=len(failed))
    print(f"\n[separate] done={done} skipped={skipped} failed={len(failed)}")
    for tag, err in failed:
        print(f"  {tag}: {err}")


if __name__ == "__main__":
    main()
