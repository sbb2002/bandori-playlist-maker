"""Step 2 — Demucs vocal separation for the 30(+9) selected tracks.

Resume-safe: skips tracks whose vocals.wav already exists.
"""
import os
import subprocess
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SEL_CSV = os.path.join(HERE, "selected_songs.csv")
LOCAL_AUDIO_DIR = r"C:\Users\user\Documents\myprojects\bandori-song-sorter\src\content\cluster\audio_full"
DL_AUDIO_DIR = os.path.join(HERE, "audio_dl")
STEMS_DIR = os.path.join(HERE, "stems")
MODEL = "htdemucs"


def audio_path(row):
    local = os.path.join(LOCAL_AUDIO_DIR, row.tag + ".wav")
    if os.path.isfile(local):
        return local
    dl = os.path.join(DL_AUDIO_DIR, row.tag + ".wav")
    return dl if os.path.isfile(dl) else None


def main():
    df = pd.read_csv(SEL_CSV)
    targets = list(df.itertuples())
    print(f"[separate] {len(targets)} tracks")

    done, skipped, failed = 0, 0, []
    for n, r in enumerate(targets, 1):
        voc_out = os.path.join(STEMS_DIR, MODEL, r.tag, "vocals.wav")
        if os.path.isfile(voc_out):
            print(f"[{n}/{len(targets)}] skip {r.tag} (already separated)")
            skipped += 1
            continue
        src = audio_path(r)
        if src is None:
            print(f"[{n}/{len(targets)}] MISSING SOURCE {r.tag}")
            failed.append((r.tag, "no source audio"))
            continue
        print(f"[{n}/{len(targets)}] separating {r.tag} ...", flush=True)
        cmd = [sys.executable, "-m", "demucs", "-n", MODEL,
               "--two-stems", "vocals", "-o", STEMS_DIR, src]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.isfile(voc_out):
            failed.append((r.tag, proc.stderr[-500:]))
            print(f"    FAILED")
        else:
            print(f"    ok")
            done += 1

    print(f"\n[separate] done={done} skipped={skipped} failed={len(failed)}")
    for tag, err in failed:
        print(f"  {tag}: {err}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
