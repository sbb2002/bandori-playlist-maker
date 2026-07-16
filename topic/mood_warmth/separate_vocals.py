"""Step 1 — Vocal separation via Demucs (htdemucs, two-stems=vocals).

Separates 32 target tracks (29 labeled + 3 anchors) into vocals/no_vocals stems.
Resume-safe: skips tracks whose vocals.wav already exists.
Output: mood_warmth/stems/htdemucs/<band>__<idx>/vocals.wav
"""
import io
import os
import subprocess
import sys
import time

import pandas as pd

# UTF-8 stdout (Windows console defaults to cp949 -> UnicodeEncodeError on JP titles)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = r"C:\Users\User\Documents\pyworks\bandori-song-sorter\src\content\cluster\audio_full"
WORKSHEET = os.path.join(HERE, "candidates_worksheet.csv")
STEMS_DIR = os.path.join(HERE, "stems")
MODEL = "htdemucs"

# 3 anchors (band, idx) — excluded from stats, needed for separation
ANCHORS = [("morfonica", 208), ("morfonica", 196), ("ave_mujica", 78)]


def build_targets():
    df = pd.read_csv(WORKSHEET)
    # exclude the duplicate row (rank 19, idx 97) whose rating is "-"
    df = df[df["similarity_rating_1to5"].astype(str).str.strip() != "-"]
    labeled = [(str(b), int(i)) for b, i in zip(df["band"], df["idx"])]
    targets = labeled + ANCHORS
    # de-dup while preserving order
    seen, out = set(), []
    for b, i in targets:
        k = (b, i)
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def track_name(band, idx):
    return f"{band}__{idx:03d}"


def source_wav(band, idx):
    return os.path.join(AUDIO_DIR, track_name(band, idx) + ".wav")


def vocals_out(band, idx):
    return os.path.join(STEMS_DIR, MODEL, track_name(band, idx), "vocals.wav")


def main():
    targets = build_targets()
    print(f"[separate] {len(targets)} target tracks")
    os.makedirs(STEMS_DIR, exist_ok=True)

    done, skipped, failed = 0, 0, []
    for n, (band, idx) in enumerate(targets, 1):
        src = source_wav(band, idx)
        out = vocals_out(band, idx)
        tag = track_name(band, idx)
        if not os.path.isfile(src):
            print(f"[{n}/{len(targets)}] MISSING SOURCE {src}", flush=True)
            failed.append((tag, "missing source"))
            continue
        if os.path.isfile(out):
            print(f"[{n}/{len(targets)}] skip {tag} (already separated)", flush=True)
            skipped += 1
            continue
        print(f"[{n}/{len(targets)}] separating {tag} ...", flush=True)
        t0 = time.time()
        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems=vocals", "-n", MODEL,
            "-o", STEMS_DIR, src,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not os.path.isfile(out):
            print(f"    FAILED rc={proc.returncode}", flush=True)
            print("    STDERR tail:", (proc.stderr or "")[-800:], flush=True)
            failed.append((tag, f"rc={proc.returncode}"))
            continue
        print(f"    ok in {time.time()-t0:.0f}s", flush=True)
        done += 1

    print(f"\n[separate] done={done} skipped={skipped} failed={len(failed)}")
    if failed:
        for tag, why in failed:
            print(f"  FAIL {tag}: {why}")

    # final verification
    present = sum(1 for b, i in targets if os.path.isfile(vocals_out(b, i)))
    print(f"[separate] vocals.wav present for {present}/{len(targets)} tracks")
    return 0 if present == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
