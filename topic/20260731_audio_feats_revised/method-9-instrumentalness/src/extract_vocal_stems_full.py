"""736곡 전수 vocals/no_vocals 2-stem 분리 (in-process 배치 demucs, GPU 상주 모델).

배경
----
기존에는 30곡분(band당 3곡)만 htdemucs 2-stem(vocals/no_vocals) 분리가 되어있어
method-9-instrumentalness·method-11-speechiness의 stem 기반 지표(instrumentalness_stem,
speechiness_stem)가 전수 확장되지 못하고 있었다. 이 스크립트는 demucs 모델(htdemucs)을
프로세스 시작 시 1회만 GPU에 로드하고, in-process `apply_model()` API로 나머지 곡을
순회하며 vocals/no_vocals 스템 wav만 생성한다(지표 계산은 하지 않음 -- 그건 후속 세션).

demucs.separate.load_track/CLI가 하던 정규화(ref.mean()/ref.std())와 리샘플링
(convert_audio)을 재현해 기존 30곡(CLI `_demucs_run.py --two-stems vocals`로 생성)과
동등한 방식으로 맞췄다. no_vocals는 vocals를 제외한 나머지 소스(drums+bass+other)를
합산해서 만든다(htdemucs CLI --two-stems 방식과 동일).

저장 위치 (기존 30곡과 동일 규칙 -- 반드시 file_idx로 폴더명을 만들 것)
--------
`bandori-playlist-maker/topic/mfcc_analysis/stems/htdemucs/<band>__<file_idx:03d>/`
  - vocals.wav
  - no_vocals.wav

재개(resume)
------------
- 이미 vocals.wav + no_vocals.wav가 둘 다 존재하는 폴더는 건너뛴다(기존 30곡 포함).
- 처리 중 진행 로그(10곡마다 진행률/ETA)를 콘솔에 출력한다(별도 CSV 기록 없음 --
  이 스크립트의 산출물은 wav 파일 자체이며, 존재 여부로 완료를 판단한다).
- 실패한 곡은 건너뛰고 계속 진행하며, 마지막에 실패 목록을 출력한다.

실행
----
    python src/extract_vocal_stems_full.py               # 전곡
    python src/extract_vocal_stems_full.py --limit 5      # 테스트
    python src/extract_vocal_stems_full.py --device cuda
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
import torch

warnings.filterwarnings("ignore")

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_TOPIC_DIR = _METHOD_DIR.parent
_REPO_ROOT = _TOPIC_DIR.parents[1]
_MYPROJECTS_ROOT = _REPO_ROOT.parent

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
AUDIO_DIR = _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
VOCAL_STEM_DIR = (
    _MYPROJECTS_ROOT / "bandori-playlist-maker" / "topic" / "mfcc_analysis" / "stems" / "htdemucs"
)


# ---------------------------------------------------------------------------
# demucs: 모델 1회 로드 + in-process vocals/no_vocals 분리
# ---------------------------------------------------------------------------
def load_demucs_model(device: str = "cuda"):
    from demucs.pretrained import get_model

    model = get_model("htdemucs")
    model.to(device)
    model.eval()
    return model


def separate_vocals(model, audio_path: Path, device: str = "cuda"):
    """오디오 파일을 읽어 (vocals, no_vocals) 텐서 쌍과 samplerate를 반환.

    demucs.separate.load_track + CLI --two-stems 절차를 재현:
      ref = wav.mean(0); wav = (wav - ref.mean()) / ref.std()
      ... apply_model ...
      source = source * ref.std() + ref.mean()
      no_vocals = sum(모든 소스 except vocals)
    """
    from demucs.apply import apply_model
    from demucs.audio import convert_audio

    data, sr = sf.read(str(audio_path), dtype="float32", always_2d=True)  # (frames, ch)
    wav = torch.from_numpy(np.ascontiguousarray(data.T))  # (ch, frames)
    wav = convert_audio(wav, sr, model.samplerate, model.audio_channels)

    ref = wav.mean(0)
    ref_mean = ref.mean()
    ref_std = ref.std()
    wav_norm = (wav - ref_mean) / (ref_std + 1e-9)

    wav_norm = wav_norm.to(device)
    with torch.no_grad():
        sources = apply_model(
            model, wav_norm[None], device=device, shifts=1, split=True,
            overlap=0.25, progress=False,
        )[0]  # (sources, channels, length)

    sources = sources.cpu() * ref_std + ref_mean

    vocals_idx = model.sources.index("vocals")
    vocals = sources[vocals_idx]
    no_vocals = sum(
        sources[i] for i in range(len(model.sources)) if i != vocals_idx
    )
    return vocals, no_vocals, model.samplerate


def extract_vocal_stem_pair(model, audio_path: Path, stem_dir: Path, device: str = "cuda") -> None:
    vocals, no_vocals, sr = separate_vocals(model, audio_path, device=device)
    stem_dir.mkdir(parents=True, exist_ok=True)
    sf.write(str(stem_dir / "vocals.wav"), vocals.numpy().T, sr)
    sf.write(str(stem_dir / "no_vocals.wav"), no_vocals.numpy().T, sr)


# ---------------------------------------------------------------------------
# 메인 루프
# ---------------------------------------------------------------------------
def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="vocals/no_vocals 2-stem 736곡 전수 분리 (GPU 상주 배치)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--device", type=str, default="cuda")
    args = ap.parse_args()

    master = pd.read_csv(MASTER_CSV)
    print(f"songs_master: {len(master)}곡", flush=True)

    device = args.device if torch.cuda.is_available() else "cpu"
    if device != args.device:
        print(f"[WARN] CUDA 사용 불가 -> {device}로 폴백", flush=True)

    tasks = []
    n_skip_done = 0
    n_skip_noaudio = 0
    for _, m in master.iterrows():
        idx = int(m["idx"])
        band = m["band"]
        song = m["song"]
        file_idx = int(m["file_idx"]) if pd.notna(m.get("file_idx")) else idx
        audio_path = AUDIO_DIR / f"{band}__{file_idx:03d}.wav"
        stem_dir = VOCAL_STEM_DIR / f"{band}__{file_idx:03d}"
        vocals_wav = stem_dir / "vocals.wav"
        no_vocals_wav = stem_dir / "no_vocals.wav"

        if vocals_wav.exists() and no_vocals_wav.exists():
            n_skip_done += 1
            continue
        if not audio_path.exists():
            n_skip_noaudio += 1
            print(f"  [SKIP] idx={idx} {band} file_idx={file_idx}: 오디오 없음 ({audio_path.name})", flush=True)
            continue

        tasks.append((idx, band, song, file_idx, audio_path, stem_dir))
        if args.limit is not None and len(tasks) >= args.limit:
            break

    print(
        f"이미완료(resume-skip)={n_skip_done}  오디오없음-skip={n_skip_noaudio}  "
        f"이번 처리 대상={len(tasks)}곡",
        flush=True,
    )
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료 또는 대상 없음).", flush=True)
        return

    print(f"demucs(htdemucs) 모델 로드 중... device={device}", flush=True)
    t_load = time.time()
    model = load_demucs_model(device=device)
    print(f"모델 로드 완료 ({time.time()-t_load:.1f}s)", flush=True)

    n_ok = n_err = 0
    failed = []
    t_start = time.time()

    for i, (idx, band, song, file_idx, audio_path, stem_dir) in enumerate(tasks, 1):
        try:
            extract_vocal_stem_pair(model, audio_path, stem_dir, device=device)
            n_ok += 1
        except torch.cuda.OutOfMemoryError as exc:
            n_err += 1
            failed.append((idx, band, song, f"OOM: {repr(exc)[:150]}"))
            print(f"  [OOM] idx={idx} {band} {str(song)[:30]}: {repr(exc)[:150]}", flush=True)
            if device == "cuda":
                torch.cuda.empty_cache()
        except Exception as exc:
            n_err += 1
            failed.append((idx, band, song, repr(exc)))
            print(f"  [ERR] idx={idx} {band} {str(song)[:30]}: {repr(exc)[:150]}", flush=True)
        finally:
            if device == "cuda":
                torch.cuda.empty_cache()

        if i % 10 == 0 or i == len(tasks):
            el = time.time() - t_start
            rate = i / el if el > 0 else 0
            eta = (len(tasks) - i) / rate if rate > 0 else 0
            print(
                f"  진행 {i}/{len(tasks)}  ok={n_ok} err={n_err}  "
                f"{rate:.3f}곡/s  ETA {eta/60:.1f}분  경과 {el/60:.1f}분",
                flush=True,
            )

    total_min = (time.time() - t_start) / 60
    print(f"완료: ok={n_ok} err={n_err}  총 {total_min:.1f}분", flush=True)
    if failed:
        print("실패 목록:", flush=True)
        for idx, band, song, err in failed:
            print(f"  idx={idx} {band} {str(song)[:40]}: {err[:120]}", flush=True)
    print(f"산출: {VOCAL_STEM_DIR}", flush=True)


if __name__ == "__main__":
    main()
