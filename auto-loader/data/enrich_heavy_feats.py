"""무거운 3개 오디오 지표 주기적 보강 스크립트.

목표: songs_master.csv의 m6-valence_median, m9-instr_stem_ratio, m11-speech_median을
     주기적으로 실측 데이터로 보강(라이브 오토로더는 의존성 때문에 실행하지 않음).

의존성: essentia-tensorflow, torch, librosa, scipy (WSL2에서만 설치 가능)
        - 하나라도 없으면 명확한 한국어 안내 후 조용히 종료(fail-soft)

동작:
  1. 의존성 체크 (essentia, torch, librosa, scipy)
  2. songs_master.csv에서 빈 행 탐지 (m6/m9/m11 중 하나라도 비어있는 행)
  3. 각 곡의 wav 로컬 캐시에서 탐색 (기존 autoloader의 audio_dir 준수)
  4. 3개 파이프라인 실행 (각 곡별 실패는 스킵, 전체 배치는 계속)
  5. CSV 안전한 부분-패치 (merge_data.patch_intensity_rows 패턴 모방)

실행:
    python auto-loader/data/enrich_heavy_feats.py

주의:
  - 모델 파일 경로(essentia): WSL2에서 직접 실행하면 essentia 자체가 모델을 로드함.
    경로가 필요하면 bpm-research/method-6-valence/extract_valence.py 참조.
  - 보컬 스템이 없으면(661곡 중 ~30곡만 존재) 해당 곡은 자동 스킵(정상).
  - 실패 시 자동 롤백: CSV 스냅샷을 유지하다 예외 발생 시 원본 복원.
"""
from __future__ import annotations

import csv
import io
import sys
import os
from pathlib import Path
from typing import Optional

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parents[1]

# --- 의존성 가용성 체크 ---
_ESSENTIA_AVAILABLE = False
_TORCH_AVAILABLE = False
_LIBROSA_AVAILABLE = False
_SCIPY_AVAILABLE = False
_ESSENTIA_ERROR = None

try:
    import essentia.standard as es
    _ESSENTIA_AVAILABLE = True
except ImportError as e:
    _ESSENTIA_ERROR = str(e)

try:
    import torch  # noqa: F401
    _TORCH_AVAILABLE = True
except ImportError:
    pass

try:
    import librosa  # noqa: F401
    _LIBROSA_AVAILABLE = True
except ImportError:
    pass

try:
    import scipy  # noqa: F401
    _SCIPY_AVAILABLE = True
except ImportError:
    pass

# --- 경로 ---
# 주의: songs_master.csv는 이 저장소(bpm-tools) 안에 없다 — data/ 디렉토리는 별도
# `data` 브랜치 워크트리(예: bpm-data-branch)에만 존재한다(run_autoloader.py의
# --repo-root와 동일한 사정). 아래 기본값은 형제 디렉토리 관례를 따른 추정치이고,
# main()의 --repo-root/--audio-dir/--stem-dir 인자로 덮어쓸 수 있다.
_MYPROJECTS_ROOT = REPO_ROOT.parent
_MASTER_CSV = _MYPROJECTS_ROOT / "bpm-data-branch" / "data" / "songs_master.csv"
_AUDIO_DIR = (
    _MYPROJECTS_ROOT
    / "bandori-song-sorter"
    / "src" / "content" / "cluster" / "audio_full"
)

# 보컬 스템 디렉토리 (method-9, method-11 용) — mfcc_analysis 연구는
# bandori-playlist-maker 저장소에 있다(bpm-tools 아님, 경로 정정).
_VOCAL_STEM_DIR = (
    _MYPROJECTS_ROOT
    / "bandori-playlist-maker"
    / "topic" / "mfcc_analysis" / "stems" / "htdemucs"
)


def _check_dependencies() -> bool:
    """의존성 체크. 부족하면 명확한 한국어 안내 후 False 반환 (exit 아님)."""
    missing = []

    if not _ESSENTIA_AVAILABLE:
        missing.append("essentia-tensorflow")

    if not _LIBROSA_AVAILABLE:
        missing.append("librosa")

    if not _SCIPY_AVAILABLE:
        missing.append("scipy")

    if missing:
        print(
            f"\n[ERROR] 필수 라이브러리가 설치되지 않았습니다: {', '.join(missing)}",
            "이 스크립트는 WSL2 환경에서만 실행 가능합니다.",
            f"WSL2에서 다음을 실행하세요:",
            f"  pip install essentia-tensorflow librosa scipy",
            sep="\n",
            flush=True,
        )
        return False

    return True


def _find_master_rows_needing_enrichment(limit: int | None = None,
                                         only_idx: set[int] | None = None
                                         ) -> list[dict]:
    """songs_master.csv를 읽어 m6/m9/m11 중 하나라도 비어있는 행 반환.

    limit: 앞에서부터 N개만(스모크테스트용). only_idx: 지정된 idx만(스모크테스트용).
    """
    if not _MASTER_CSV.exists():
        print(f"[ERROR] {_MASTER_CSV} 파일 없음")
        return []

    rows = []
    with _MASTER_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            idx = r.get("idx", "").strip()
            m6 = (r.get("m6-valence_median") or "").strip()
            m9 = (r.get("m9-instr_stem_ratio") or "").strip()
            m11 = (r.get("m11-speech_median") or "").strip()
            # 셋 중 하나라도 비어있으면 대상
            if not (idx and (not m6 or not m9 or not m11)):
                continue
            if only_idx is not None and int(idx) not in only_idx:
                continue
            rows.append(r)
            if limit is not None and len(rows) >= limit:
                break

    return rows


def _audio_path(band: str, idx: int) -> Path:
    """오디오 캐시 경로 (fetch_new.wav_path 동일)."""
    return _AUDIO_DIR / f"{band}__{idx:03d}.wav"


def _vocal_stem_paths(band: str, idx: int) -> Optional[tuple[Path, Path]]:
    """보컬/악기 스템 폴더 확인. 존재하면 (vocals.wav, no_vocals.wav) 튜플."""
    stem_dir = _VOCAL_STEM_DIR / f"{band}__{idx:03d}"
    if not stem_dir.is_dir():
        return None
    vocal_path = stem_dir / "vocals.wav"
    instr_path = stem_dir / "no_vocals.wav"
    if vocal_path.exists() and instr_path.exists():
        return vocal_path, instr_path
    return None


def extract_valence(audio_path: Path) -> Optional[float]:
    """
    단일 오디오에서 valence_median 추출 (essentia emoMusic 기반).

    참고: 모델 파일(msd-musicnn-1.pb, emomusic-msd-musicnn-2.pb)이 필요하나,
    이 환경(bandori-playlist-maker 로컬)에는 보통 없음.
    bpm-research 로컬에서 모델을 찾아 경로를 설정해야 함(WSL2 전제).

    실패 시 None 반환 (fail-soft).
    """
    if not _ESSENTIA_AVAILABLE:
        return None

    try:
        import numpy as np

        SR = 16000

        # 오디오 로드
        loader = es.MonoLoader(filename=str(audio_path), sampleRate=SR)
        audio = loader()

        # essentia 모델 로드 시도
        # 모델 경로는 환경 변수 또는 bpm-research에서 찾아야 함
        embedding_model_path = os.environ.get(
            "ESSENTIA_EMBEDDING_MODEL",
            None,
        )
        head_model_path = os.environ.get(
            "ESSENTIA_EMOMUSIC_MODEL",
            None,
        )

        if not embedding_model_path or not head_model_path:
            # 모델 경로 없음 — 정상 (이 환경에선 보통 없음)
            return None

        embedding_model_path = Path(embedding_model_path)
        head_model_path = Path(head_model_path)

        if not embedding_model_path.exists() or not head_model_path.exists():
            return None

        # 2단계 모델 로드
        embedding_model = es.TensorflowPredictMusiCNN(
            graphFilename=str(embedding_model_path), output="model/dense/BiasAdd"
        )
        head_model = es.TensorflowPredict2D(
            graphFilename=str(head_model_path), output="model/Identity"
        )

        # 임베딩 추출
        embeddings = embedding_model(audio)
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings, dtype=np.float32)

        # 회귀 예측 (valence, arousal)
        preds = head_model(embeddings)
        if not isinstance(preds, np.ndarray):
            preds = np.array(preds, dtype=np.float32)

        # valence 컬럼(인덱스 0) 추출
        valence_series = preds[:, 0].astype(np.float32)

        # 중앙값
        valence_median = float(np.median(valence_series))
        return round(valence_median, 4)

    except Exception as e:
        # fail-soft: 예외는 로그하지 않음 (expect 구간)
        return None


def extract_instr_stem_ratio(band: str, idx: int) -> Optional[float]:
    """
    보컬 스템 에너지비 기반 instrumentalness 계산.
    스템이 없으면 None (정상 — 아직 전체 카탈로그에 스템이 없음).
    """
    paths = _vocal_stem_paths(band, idx)
    if paths is None:
        return None  # 스템 없음

    try:
        import librosa
        import numpy as np

        vocal_path, instr_path = paths
        SR = 22050

        # 스템 로드
        y_vocal, _ = librosa.load(str(vocal_path), sr=SR, mono=True)
        y_instr, _ = librosa.load(str(instr_path), sr=SR, mono=True)

        # 에너지 계산 (L2 norm의 제곱)
        vocal_energy = float(np.sum(y_vocal ** 2))
        instr_energy = float(np.sum(y_instr ** 2))
        total_energy = vocal_energy + instr_energy

        if total_energy > 0:
            ratio = 1.0 - (vocal_energy / total_energy)
        else:
            ratio = 0.0

        return round(ratio, 6)

    except Exception as e:
        return None


def extract_speech_median(band: str, idx: int) -> Optional[float]:
    """
    Scheirer-Slaney 4Hz 변조 에너지로 speechiness 추출 (보컬 스템 기반).
    스템이 없으면 None (정상).

    참고: method-11-speechiness/extract_speechiness_stem.py의 modulation_energy_ratio() 포팅.
    """
    paths = _vocal_stem_paths(band, idx)
    if paths is None:
        return None  # 스템 없음

    try:
        import librosa
        import numpy as np
        from scipy import signal

        vocal_path, _ = paths
        SR = 22050

        # 보컬 스템 로드
        y, _ = librosa.load(str(vocal_path), sr=SR, mono=True)

        # Envelope 추출: 정류 → 저역통과
        y_rectified = np.abs(y)
        nyquist = SR / 2.0
        low_cutoff = 20.0 / nyquist
        b, a = signal.butter(2, low_cutoff, btype="low")

        try:
            y_envelope = signal.filtfilt(b, a, y_rectified)
        except Exception:
            y_envelope = signal.lfilter(b, a, y_rectified)

        # 프레임 분할 (1초, 50% 겹침)
        frame_sec = 1.0
        frame_samples = int(frame_sec * SR)
        hop_samples = int(frame_samples * 0.5)

        n_frames = max(1, (len(y_envelope) - frame_samples) // hop_samples + 1)

        modulation_ratios = []

        for frame_idx in range(n_frames):
            start = frame_idx * hop_samples
            end = start + frame_samples

            if end > len(y_envelope):
                end = len(y_envelope)
                if end - start < frame_samples // 2:
                    break

            frame_envelope = y_envelope[start:end]

            # FFT (Hann 윈도우)
            window = signal.windows.hann(len(frame_envelope))
            frame_windowed = frame_envelope * window

            spec = np.fft.rfft(frame_windowed)
            freqs = np.fft.rfftfreq(len(frame_windowed), d=1.0 / SR)
            power = np.abs(spec) ** 2

            # 3~4Hz 대역 에너지
            band_3_4_mask = (freqs >= 3.0) & (freqs <= 4.0)
            energy_3_4 = np.sum(power[band_3_4_mask])

            # 전체 변조 대역(0.5~20Hz) 에너지
            modulation_mask = (freqs >= 0.5) & (freqs <= 20.0)
            energy_modulation = np.sum(power[modulation_mask])

            # 비율 계산
            if energy_modulation > 0:
                ratio = energy_3_4 / energy_modulation
            else:
                ratio = 0.0

            ratio = max(0.0, min(1.0, ratio))  # [0, 1] clamp
            modulation_ratios.append(ratio)

        if not modulation_ratios:
            return None

        # 중앙값
        speech_median = float(np.median(modulation_ratios))
        return round(speech_median, 6)

    except Exception as e:
        return None


def _line_terminator(raw: bytes) -> str:
    """CSV 개행 문자 감지 (merge_data.py 동일)."""
    return "\r\n" if b"\r\n" in raw[:4096] else "\n"


def patch_csv(updates: dict[int, dict[str, str]]) -> bool:
    """
    songs_master.csv의 특정 idx 행에 m6/m9/m11 컬럼만 갱신.
    스냅샷 기반 안전한 부분-패치 (merge_data.patch_intensity_rows 패턴).
    성공하면 True, 실패하면 False (롤백됨).
    """
    if not updates:
        return True

    if not _MASTER_CSV.exists():
        print(f"[ERROR] {_MASTER_CSV} 파일 없음")
        return False

    # 스냅샷
    snapshot = _MASTER_CSV.read_bytes()

    try:
        # 행 읽기
        with _MASTER_CSV.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)

        if fieldnames is None:
            print("[ERROR] 헤더 없는 CSV")
            return False

        # 부분 갱신
        patched = 0
        for r in rows:
            try:
                idx = int(r["idx"])
            except (ValueError, KeyError):
                continue

            u = updates.get(idx)
            if u is None:
                continue

            # m6, m9, m11만 갱신 (다른 필드는 건드리지 않음)
            for k in ["m6-valence_median", "m9-instr_stem_ratio", "m11-speech_median"]:
                if k in u and u[k]:
                    r[k] = u[k]
            patched += 1

        if patched != len(updates):
            found = {int(r["idx"]) for r in rows if "idx" in r} & set(updates.keys())
            missing = set(updates.keys()) - found
            raise AssertionError(
                f"idx 못 찾음(보강 대상 아님?): {sorted(missing)}"
            )

        # 개행 방식 유지
        term = _line_terminator(snapshot)

        # 파일 재작성
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator=term)
        writer.writeheader()
        writer.writerows(rows)

        _MASTER_CSV.write_bytes(buf.getvalue().encode("utf-8"))
        print(f"[OK] {patched}개 행 갱신 완료")
        return True

    except Exception as e:
        print(f"[ERROR] CSV 패치 실패: {e}")
        # 롤백
        _MASTER_CSV.write_bytes(snapshot)
        print("[ROLLBACK] 원본 복원 완료")
        return False


def _parse_args():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=None,
                   help="data/songs_master.csv를 담은 data 브랜치 워크트리 경로 "
                        "(기본: 형제 디렉토리 bpm-data-branch)")
    p.add_argument("--audio-dir", type=Path, default=None,
                   help="전곡 wav 캐시 디렉토리 (기본: 형제 bandori-song-sorter의 audio_full)")
    p.add_argument("--stem-dir", type=Path, default=None,
                   help="보컬/악기 스템 디렉토리 (기본: 형제 bandori-playlist-maker의 "
                        "topic/mfcc_analysis/stems/htdemucs)")
    p.add_argument("--limit", type=int, default=None,
                   help="스모크테스트용: 보강 대상 앞에서부터 N개만 처리")
    p.add_argument("--idx", type=str, default=None,
                   help="스모크테스트용: 쉼표로 구분한 idx만 처리(예: --idx 24,25)")
    return p.parse_args()


def main():
    global _MASTER_CSV, _AUDIO_DIR, _VOCAL_STEM_DIR

    args = _parse_args()
    if args.repo_root is not None:
        _MASTER_CSV = args.repo_root / "data" / "songs_master.csv"
    if args.audio_dir is not None:
        _AUDIO_DIR = args.audio_dir
    if args.stem_dir is not None:
        _VOCAL_STEM_DIR = args.stem_dir
    only_idx = {int(x) for x in args.idx.split(",")} if args.idx else None

    # 인코딩 설정
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass

    print("[1/4] 의존성 확인...")
    if not _check_dependencies():
        print("\n[ABORT] 필수 의존성 부족.")
        sys.exit(1)

    print("[OK] essentia, librosa, scipy 모두 available")
    print(f"[경로] master={_MASTER_CSV}  audio={_AUDIO_DIR}  stems={_VOCAL_STEM_DIR}")

    print("\n[2/4] 보강 대상 행 탐지...")
    target_rows = _find_master_rows_needing_enrichment(limit=args.limit, only_idx=only_idx)
    if not target_rows:
        print("[OK] 보강 대상 없음")
        sys.exit(0)

    print(f"[OK] {len(target_rows)}개 행 필요")

    print("\n[3/4] 오디오 특징 추출 중...")
    updates: dict[int, dict[str, str]] = {}
    skipped = 0
    extracted = 0

    for i, row in enumerate(target_rows, 1):
        try:
            idx = int(row["idx"])
            band = row["band"]
            song = row["song"]

            print(f"  [{i}/{len(target_rows)}] idx={idx} {band} - {song}")

            # 오디오 경로 확인
            audio_path = _audio_path(band, idx)
            if not audio_path.exists():
                print(f"    [SKIP] 오디오 없음")
                skipped += 1
                continue

            updates[idx] = {}

            # m6-valence_median
            if not (row.get("m6-valence_median") or "").strip():
                v = extract_valence(audio_path)
                if v is not None:
                    updates[idx]["m6-valence_median"] = str(v)
                    extracted += 1

            # m9-instr_stem_ratio
            if not (row.get("m9-instr_stem_ratio") or "").strip():
                r = extract_instr_stem_ratio(band, idx)
                if r is not None:
                    updates[idx]["m9-instr_stem_ratio"] = str(r)
                    extracted += 1

            # m11-speech_median
            if not (row.get("m11-speech_median") or "").strip():
                s = extract_speech_median(band, idx)
                if s is not None:
                    updates[idx]["m11-speech_median"] = str(s)
                    extracted += 1

            if not updates[idx]:
                del updates[idx]

        except Exception as e:
            print(f"    [ERROR] {e}")
            continue

    if not updates:
        print(f"\n[RESULT] 추출된 값이 없습니다. (skipped={skipped})")
        sys.exit(0)

    print(f"\n[4/4] CSV 갱신 중... ({len(updates)}개 행, 총 {extracted}개 값 추출, {skipped}개 스킵)")
    if patch_csv(updates):
        print("\n[SUCCESS] 보강 완료")
        sys.exit(0)
    else:
        print("\n[FAILURE] CSV 갱신 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
