"""전곡 프레임별 강도(intensity) 시계열 → 시간분절 통계 추출.

사용자 제안(2026-07-11): 곡별 단일 스칼라 집계는 "한 순간이라도 시끄러워지는" 곡(Steer to
Utopia 등)을 못 잡는다. 프레임별 강도를 구해 **start(0~15s) / end(마지막 15s) / max / min /
mean / std** 를 산출하면, "조용 = 절대 시끄러워지지 않음(낮은 max)" 을 판정할 수 있다.

프레임별 강도 = 음색·리듬 피처(centroid, bandwidth, zcr, flatness, onset, rms)를 전역
robust z-정규화한 평균. (raw RMS 절대값은 라우드니스 정규화라 무용하나, 다른 피처와 결합 +
전역 정규화로 상대 신호로 사용.)

출력: data/temporal_intensity.csv (idx, band, song, i_mean, i_std, i_max, i_min, i_start, i_end;
      i_* 는 전역 z 스케일. percentile 정규화는 소비 측(song_repo)에서 수행.)

실행: python auto-loader/data/extract_temporal_intensity.py
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import librosa
import numpy as np

_REPO = Path(__file__).resolve().parents[2]
_MASTER = _REPO / "data" / "songs_master.csv"
_AUDIO = Path("C:/Users/User/Documents/pyworks/bandori-song-sorter/src/content/cluster/audio_full")
_OUT = _REPO / "data" / "temporal_intensity.csv"

SR = 22050
HOP = 512
SEG_SEC = 15.0
FEATS = ["centroid", "bandwidth", "zcr", "flatness", "onset", "rms"]


def _frame_features(y: np.ndarray) -> np.ndarray:
    """(n_frames, 6) 프레임별 raw 피처."""
    S = np.abs(librosa.stft(y, hop_length=HOP))
    cen = librosa.feature.spectral_centroid(S=S, sr=SR)[0]
    bw = librosa.feature.spectral_bandwidth(S=S, sr=SR)[0]
    flat = librosa.feature.spectral_flatness(S=S)[0]
    rms = librosa.feature.rms(S=S)[0]
    zcr = librosa.feature.zero_crossing_rate(y, hop_length=HOP)[0]
    onset = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    n = min(len(cen), len(bw), len(flat), len(rms), len(zcr), len(onset))
    return np.stack([cen[:n], bw[:n], flat[:n], zcr[:n], onset[:n], rms[:n]], axis=1)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass
    rows = list(csv.DictReader(_MASTER.open(encoding="utf-8", newline="")))
    t0 = time.time()

    per_song: dict[int, np.ndarray] = {}
    meta: dict[int, dict] = {}
    for i, r in enumerate(rows):
        idx = int(r["idx"])
        fn = _AUDIO / f"{r['band']}__{idx:03d}.wav"
        if not fn.exists():
            print(f"[skip] {fn.name} 없음")
            continue
        try:
            y, _ = librosa.load(fn, sr=SR, mono=True)
            per_song[idx] = _frame_features(y).astype(np.float32)
            meta[idx] = {"band": r["band"], "song": r["song"]}
        except Exception as e:  # noqa: BLE001
            print(f"[err] {fn.name}: {e}")
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(rows)}  ({time.time()-t0:.0f}s)")

    # --- 전역 robust 정규화(모든 프레임 기준) ---
    allframes = np.concatenate(list(per_song.values()), axis=0)
    med = np.median(allframes, axis=0)
    mad = np.median(np.abs(allframes - med), axis=0) * 1.4826
    mad[mad < 1e-9] = allframes.std(axis=0)[mad < 1e-9] + 1e-9
    # flatness는 이미 0~1이지만 방향 동일(높을수록 노이즈=시끄러움). 전부 higher=louder.

    seg = int(SEG_SEC * SR / HOP)
    out = []
    for idx, frames in per_song.items():
        z = (frames - med) / mad          # (n,6)
        inten = z.mean(axis=1)            # 프레임별 강도(전역 z 평균)
        s = inten[:seg] if len(inten) > seg else inten
        e = inten[-seg:] if len(inten) > seg else inten
        out.append({
            "idx": idx, "band": meta[idx]["band"], "song": meta[idx]["song"],
            "i_mean": f"{inten.mean():.5f}", "i_std": f"{inten.std():.5f}",
            "i_max": f"{np.percentile(inten, 95):.5f}",   # robust max
            "i_min": f"{np.percentile(inten, 5):.5f}",    # robust min
            "i_start": f"{s.mean():.5f}", "i_end": f"{e.mean():.5f}",
        })

    out.sort(key=lambda r: r["idx"])
    with _OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["idx", "band", "song", "i_mean", "i_std", "i_max", "i_min", "i_start", "i_end"])
        w.writeheader()
        w.writerows(out)
    print(f"\n[DONE] {len(out)}곡 → {_OUT.name}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
