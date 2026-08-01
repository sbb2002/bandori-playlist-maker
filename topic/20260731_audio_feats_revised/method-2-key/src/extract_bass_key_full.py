"""베이스 스템 key 검증: 736곡 전체 (in-process 배치 demucs, GPU 상주 모델).

배경
----
기존 `_expand_bass_50.py`는 곡마다 subprocess로 demucs CLI를 새로 띄워 매번 모델을
재로드했다(50곡 표본까지는 감내 가능했으나 736곡 전체로는 오버헤드가 누적됨).
이 스크립트는 demucs 모델을 프로세스 시작 시 1회만 GPU에 로드하고, in-process
`apply_model()` API로 736곡을 순회하며 베이스 스템을 분리한다.

demucs.separate.load_track/CLI가 하던 정규화(ref.mean()/ref.std())와 리샘플링
(convert_audio)을 그대로 재현해 결과가 기존 CLI 방식(_demucs_run.py, 50곡 표본)과
동등하도록 맞췄다.

산출물
------
- `out/bass_key_validation/stems/<band>__<idx:03d>/bass.wav` — 베이스 스템(재사용/재개용)
- `out/bass_key_validation/bass_key_validation_full.csv` — 736곡 전체 결과
  (기존 50행짜리 `bass_key_validation.csv`는 절대 덮어쓰지 않음 — 별도 파일)

재개(resume)
------------
- 이미 `bass.wav`가 존재하는 곡은 demucs 분리를 건너뛰고 K-S만 재적용.
- 이미 `bass_key_validation_full.csv`에 정상 기록(에러 없음)된 idx는 통째로 스킵.
- 곡마다 결과를 즉시 CSV에 append(중단돼도 이어서 가능).

실행
----
    python src/extract_bass_key_full.py               # 전곡
    python src/extract_bass_key_full.py --limit 5      # 테스트
    python src/extract_bass_key_full.py --fresh        # 처음부터
"""
from __future__ import annotations

import argparse
import csv
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
KEY_RAW_CSV = _METHOD_DIR / "out" / "csv" / "key_raw.csv"
VAL_DIR = _METHOD_DIR / "out" / "bass_key_validation"
STEMS_DIR = VAL_DIR / "stems"
OUT_CSV = VAL_DIR / "bass_key_validation_full.csv"  # 신규 파일 (기존 50행 파일 보존)

sys.path.insert(0, str(_THIS_DIR))
from extract_key_ks import _sliding_window_keys, _majority_vote, WINDOW_SEC  # noqa: E402

FIELDNAMES = [
    "idx", "band", "song",
    "key_ks", "mode_ks", "key_essentia", "mode_essentia",
    "key_bass", "mode_bass", "key_bass_confidence",
    "agree_with_ks", "agree_with_essentia", "error",
]


# ---------------------------------------------------------------------------
# demucs: 모델 1회 로드 + in-process 베이스 분리
# ---------------------------------------------------------------------------
def load_demucs_model(device: str = "cuda"):
    from demucs.pretrained import get_model

    model = get_model("htdemucs")
    model.to(device)
    model.eval()
    return model


def separate_bass(model, audio_path: Path, device: str = "cuda"):
    """오디오 파일을 읽어 베이스 스템만 분리해 (channels, length) 텐서로 반환.

    demucs.separate.load_track + CLI의 정규화 절차를 재현:
      ref = wav.mean(0); wav = (wav - ref.mean()) / ref.std()
      ... apply_model ...
      bass = bass * ref.std() + ref.mean()
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

    bass_idx = model.sources.index("bass")
    bass = sources[bass_idx].cpu()
    bass = bass * ref_std + ref_mean
    return bass, model.samplerate


def extract_bass_wav(model, audio_path: Path, out_path: Path, device: str = "cuda") -> None:
    bass, sr = separate_bass(model, audio_path, device=device)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), bass.numpy().T, sr)


# ---------------------------------------------------------------------------
# resume 지원
# ---------------------------------------------------------------------------
def _done_idxs() -> set:
    if not OUT_CSV.exists():
        return set()
    done = set()
    with OUT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if not (r.get("error") or "").strip():
                try:
                    done.add(int(r["idx"]))
                except (ValueError, KeyError):
                    continue
    return done


def _open_writer(append: bool):
    header_needed = not (OUT_CSV.exists() and OUT_CSV.stat().st_size > 0)
    mode = "a" if append else "w"
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    f = OUT_CSV.open(mode, encoding="utf-8", newline="")
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
    if header_needed or not append:
        writer.writeheader()
        f.flush()
    return f, writer


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="베이스 스템 key 검증 (736곡 전체, GPU 상주 배치)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    ap.add_argument("--fresh", action="store_true", help="기존 출력 무시하고 처음부터")
    ap.add_argument("--device", type=str, default="cuda")
    args = ap.parse_args()

    master = pd.read_csv(MASTER_CSV)
    key_raw = pd.read_csv(KEY_RAW_CSV)

    done = set() if args.fresh else _done_idxs()
    print(f"전체 {len(master)}곡, 이미완료 {len(done)}곡", flush=True)

    device = args.device if torch.cuda.is_available() else "cpu"
    if device != args.device:
        print(f"[WARN] CUDA 사용 불가 -> {device}로 폴백", flush=True)
    print(f"demucs(htdemucs) 모델 로드 중... device={device}", flush=True)
    t_load = time.time()
    model = load_demucs_model(device=device)
    print(f"모델 로드 완료 ({time.time()-t_load:.1f}s)", flush=True)

    tasks = []
    for _, m in master.iterrows():
        idx = int(m["idx"])
        if idx in done:
            continue
        tasks.append(m)
        if args.limit is not None and len(tasks) >= args.limit:
            break

    print(f"이번 처리 대상 {len(tasks)}곡", flush=True)
    if not tasks:
        print("처리할 곡이 없습니다(모두 완료).", flush=True)
        return

    append = not args.fresh
    f, writer = _open_writer(append=append)

    n_ok = n_err = 0
    failed = []
    t_start = time.time()

    try:
        for i, m in enumerate(tasks, 1):
            idx = int(m["idx"])
            band, song = m["band"], m["song"]
            file_idx = int(m["file_idx"]) if pd.notna(m.get("file_idx")) else idx
            audio_path = AUDIO_DIR / f"{band}__{file_idx:03d}.wav"
            stem_dir = STEMS_DIR / f"{band}__{idx:03d}"
            bass_wav = stem_dir / "bass.wav"

            row = {
                "idx": idx, "band": band, "song": song,
                "key_ks": "", "mode_ks": "", "key_essentia": "", "mode_essentia": "",
                "key_bass": "", "mode_bass": "", "key_bass_confidence": "",
                "agree_with_ks": "", "agree_with_essentia": "", "error": "",
            }

            try:
                if not audio_path.exists():
                    raise FileNotFoundError(f"오디오 없음: {audio_path.name}")

                if not bass_wav.exists():
                    extract_bass_wav(model, audio_path, bass_wav, device=device)
                    if device == "cuda":
                        torch.cuda.empty_cache()

                windows, dur = _sliding_window_keys(bass_wav, window_sec=WINDOW_SEC)
                agg = _majority_vote(windows)
                key_bass, mode_bass, conf = agg["key_ks"], agg["mode_ks"], agg["key_ks_confidence"]

                kr = key_raw[key_raw["idx"] == idx]
                key_ks = kr["key_ks"].values[0] if len(kr) else None
                mode_ks = kr["mode_ks"].values[0] if len(kr) else None
                key_essentia = kr["key_essentia"].values[0] if len(kr) else None
                mode_essentia = kr["mode_essentia"].values[0] if len(kr) else None

                row.update({
                    "key_ks": key_ks, "mode_ks": mode_ks,
                    "key_essentia": key_essentia, "mode_essentia": mode_essentia,
                    "key_bass": key_bass, "mode_bass": mode_bass,
                    "key_bass_confidence": conf,
                    "agree_with_ks": (key_bass == key_ks) and (mode_bass == mode_ks),
                    "agree_with_essentia": (key_bass == key_essentia) and (mode_bass == mode_essentia),
                })
                n_ok += 1
            except Exception as exc:
                row["error"] = repr(exc)
                n_err += 1
                failed.append((idx, band, song, repr(exc)))
                print(f"  [ERR] idx={idx} {band} {str(song)[:30]}: {repr(exc)[:150]}", flush=True)

            writer.writerow(row)
            f.flush()

            if i % 10 == 0 or i == len(tasks):
                el = time.time() - t_start
                rate = i / el if el > 0 else 0
                eta = (len(tasks) - i) / rate if rate > 0 else 0
                print(
                    f"  진행 {i}/{len(tasks)}  ok={n_ok} err={n_err}  "
                    f"{rate:.3f}곡/s  ETA {eta/60:.1f}분  경과 {el/60:.1f}분",
                    flush=True,
                )
    finally:
        f.close()

    total_min = (time.time() - t_start) / 60
    print(f"완료: ok={n_ok} err={n_err}  총 {total_min:.1f}분", flush=True)
    if failed:
        print("실패 목록:", flush=True)
        for idx, band, song, err in failed:
            print(f"  idx={idx} {band} {str(song)[:40]}: {err[:120]}", flush=True)
    print(f"산출: {OUT_CSV}", flush=True)


if __name__ == "__main__":
    main()
