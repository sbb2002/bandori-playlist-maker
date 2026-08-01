"""bass_key_validation을 30->50곡으로 확장 (GPU demucs + 기존 검증된 shim 재사용)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_REPO_ROOT = _METHOD_DIR.parents[2]
_MYPROJECTS_ROOT = _REPO_ROOT.parent

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
AUDIO_DIR = _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
KEY_RAW_CSV = _METHOD_DIR / "out" / "csv" / "key_raw.csv"
VAL_DIR = _METHOD_DIR / "out" / "bass_key_validation"
STEMS_DIR = VAL_DIR / "stems"
OUT_CSV = VAL_DIR / "bass_key_validation.csv"
DEMUCS_RUN = _THIS_DIR / "_demucs_run.py"

NEW_IDX = [13, 29, 149, 176, 181, 182, 254, 263, 282, 303, 306, 328, 375, 384, 419, 422, 492, 544, 553, 631]

sys.path.insert(0, str(_THIS_DIR))
from extract_key_ks import _sliding_window_keys, _majority_vote, WINDOW_SEC  # noqa: E402


def main():
    master = pd.read_csv(MASTER_CSV)
    key_raw = pd.read_csv(KEY_RAW_CSV)
    existing = pd.read_csv(OUT_CSV)
    print(f"기존: {len(existing)}행")

    rows = []
    for i, idx in enumerate(NEW_IDX, 1):
        m = master[master["idx"] == idx].iloc[0]
        band, song = m["band"], m["song"]
        file_idx = int(m["file_idx"]) if pd.notna(m.get("file_idx")) else int(idx)
        audio = AUDIO_DIR / f"{band}__{file_idx:03d}.wav"
        stem_dir = STEMS_DIR / f"{band}__{idx:03d}"
        stem_dir.mkdir(parents=True, exist_ok=True)
        bass_wav = stem_dir / "bass.wav"

        print(f"[{i}/20] idx={idx} {band} {song[:30]}", end=" ")
        if not audio.exists():
            print("SKIP(오디오없음)")
            continue

        if not bass_wav.exists():
            r = subprocess.run(
                [sys.executable, str(DEMUCS_RUN), "-n", "htdemucs", "--two-stems", "bass",
                 "-d", "cuda", "-o", str(stem_dir), str(audio)],
                capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                print(f"FAILED demucs rc={r.returncode}: {r.stderr[-300:]}")
                continue
            produced = list(stem_dir.rglob("bass.wav"))
            if not produced:
                print("FAILED(bass.wav 없음)")
                continue
            produced[0].rename(bass_wav)
            # 정리: htdemucs 하위 중간폴더 제거
            import shutil
            for d in stem_dir.iterdir():
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)

        windows, dur = _sliding_window_keys(bass_wav, window_sec=WINDOW_SEC)
        agg = _majority_vote(windows)
        key_bass, mode_bass, conf = agg["key_ks"], agg["mode_ks"], agg["key_ks_confidence"]

        kr = key_raw[key_raw["idx"] == idx]
        key_ks = kr["key_ks"].values[0] if len(kr) else None
        mode_ks = kr["mode_ks"].values[0] if len(kr) else None
        key_essentia = kr["key_essentia"].values[0] if len(kr) else None
        mode_essentia = kr["mode_essentia"].values[0] if len(kr) else None

        rows.append({
            "idx": idx, "band": band, "song": song,
            "key_ks": key_ks, "mode_ks": mode_ks,
            "key_essentia": key_essentia, "mode_essentia": mode_essentia,
            "key_bass": key_bass, "mode_bass": mode_bass,
            "key_bass_confidence": conf,
            "agree_with_ks": (key_bass == key_ks) and (mode_bass == mode_ks),
            "agree_with_essentia": (key_bass == key_essentia) and (mode_bass == mode_essentia),
        })
        print(f"OK K-S:{key_ks}/{mode_ks} Bass:{key_bass}/{mode_bass}(conf={conf:.3f})")

    new_df = pd.DataFrame(rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.drop_duplicates(subset="idx", keep="first")
    combined.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n최종 {len(combined)}행 저장: {OUT_CSV}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
