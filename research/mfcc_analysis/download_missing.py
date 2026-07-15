"""Step 1b — download the songs that have no local audio_full copy.

Only touches rows in selected_songs.csv where has_local_audio=False.
Downloads best audio, converts to wav via yt-dlp/ffmpeg, writes to audio_dl/.
"""
import os
import subprocess
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SEL_CSV = os.path.join(HERE, "selected_songs.csv")
OUT_DIR = os.path.join(HERE, "audio_dl")


def main():
    df = pd.read_csv(SEL_CSV)
    missing = df[~df["has_local_audio"]]
    print(f"[download] {len(missing)} tracks to fetch")

    failed = []
    for n, r in enumerate(missing.itertuples(), 1):
        out_path = os.path.join(OUT_DIR, r.tag + ".wav")
        if os.path.isfile(out_path):
            print(f"[{n}/{len(missing)}] skip {r.tag} (already downloaded)")
            continue
        print(f"[{n}/{len(missing)}] {r.tag}  {r.url}", flush=True)
        cmd = [
            "yt-dlp", "-x", "--audio-format", "wav",
            "-o", os.path.join(OUT_DIR, r.tag + ".%(ext)s"),
            r.url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.isfile(out_path):
            failed.append((r.tag, proc.returncode, proc.stderr[-500:]))
            print(f"  FAILED rc={proc.returncode}")
        else:
            print(f"  ok")

    if failed:
        print(f"\n[download] {len(failed)} FAILED:")
        for tag, rc, err in failed:
            print(f"  {tag}: rc={rc}\n{err}")
        sys.exit(1)
    print("[download] all done")


if __name__ == "__main__":
    main()
