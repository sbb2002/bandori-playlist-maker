"""45s center-excerpt 특징 추출 — 형제 프로젝트 로직 벤더링(신곡 분석용).

`data/song_features_with_proxies.csv`의 원시 컬럼(harmonic_ratio…voiced_frac_mix)을
기존 660곡과 **동일한 방법**으로 신곡에 대해 산출한다. 원본 로직 출처(벤더링 시점 =
bandori-song-sorter origin/main a146ede, 2026-07-15):

- `src/tools/cluster/perceptual_features.py` — `timbre()`, `mode_valence()`, `f0_p95()`
  (Krumhansl-Schmuckler 프로파일 포함)
- `src/tools/cluster/genre_features_extract.py` — `compute()`(45s center excerpt,
  SR 22050, HPSS harmonic_ratio, r5 반올림), soundfile 로드 관례(duration_s 1자리)

벤더링 이유: 형제 레포의 `side-project/genre-features/`가 이미 삭제된 전례처럼
원본 파일 이동/삭제에 파이프라인이 깨지지 않도록 스냅샷을 고정한다. **원본과 산식이
달라지면 기존 660곡과 신곡의 분포가 어긋나므로 임의 수정 금지.**

주의: librosa 0.11에서 `librosa.beat.tempo`가 `librosa.feature.rhythm.tempo`로
이동 — 두 위치를 모두 지원한다(동일 알고리즘).

외부 의존: numpy, librosa, soundfile, scipy (src/scripts README의 오디오 스택 예외).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

SR = 22050          # genre_features_extract.py와 동일
EXCERPT_SEC = 45.0  # phasec harmonic_ratio 검증 구간과 동일(전체 근사)

# Krumhansl-Schmuckler 조성 프로파일 (perceptual_features.py 원본 그대로)
KS_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KS_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

F0_MIN, F0_MAX = 110.0, 1000.0

# 산출 원시 컬럼(순서 = data/song_features_with_proxies.csv의 원시 구간과 동일)
RAW_FIELDS = ["duration_s", "harmonic_ratio", "centroid", "rolloff", "flatness",
              "contrast", "flux", "zcr", "rms", "tempo_excerpt", "mode_score",
              "key", "voiced_frac_mix"]


def _center_excerpt(y: np.ndarray, sr: int, sec: float) -> np.ndarray:
    """genre_features_extract._center_excerpt 원본 그대로."""
    n = len(y)
    w = int(sec * sr)
    if n <= w:
        return y
    start = (n - w) // 2
    return y[start:start + w]


def _tempo(y: np.ndarray, sr: int) -> float:
    """librosa 0.10(beat.tempo) / 0.11+(feature.rhythm.tempo) 양쪽 지원."""
    import librosa
    try:
        from librosa.feature.rhythm import tempo as tempo_fn  # librosa >= 0.10
    except ImportError:  # pragma: no cover - 구버전 폴백
        tempo_fn = librosa.beat.tempo
    return float(np.atleast_1d(tempo_fn(y=y, sr=sr))[0])


def timbre(y: np.ndarray, sr: int) -> dict:
    """perceptual_features.timbre 벤더링(tempo 호출 위치만 버전 호환 처리)."""
    import librosa
    cent = librosa.feature.spectral_centroid(y=y, sr=sr)
    roll = librosa.feature.spectral_rolloff(y=y, sr=sr)
    flat = librosa.feature.spectral_flatness(y=y)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
    zcr = librosa.feature.zero_crossing_rate(y)
    rms = librosa.feature.rms(y=y)
    flux = librosa.onset.onset_strength(y=y, sr=sr)
    return {
        "centroid": float(cent.mean()), "rolloff": float(roll.mean()),
        "flatness": float(flat.mean()), "contrast": float(contrast.mean()),
        "flux": float(flux.mean()), "zcr": float(zcr.mean()),
        "rms": float(rms.mean()), "tempo": _tempo(y, sr),
    }


def mode_valence(y: np.ndarray, sr: int) -> dict:
    """perceptual_features.mode_valence 벤더링 — mode_score와 key('Amaj' 형식)."""
    import librosa
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(1)
    maj = [float(np.corrcoef(chroma, np.roll(KS_MAJ, i))[0, 1]) for i in range(12)]
    mnr = [float(np.corrcoef(chroma, np.roll(KS_MIN, i))[0, 1]) for i in range(12)]
    best_maj, best_min = max(maj), max(mnr)
    is_major = best_maj >= best_min
    key = (int(np.argmax(maj)) if is_major else int(np.argmax(mnr)))
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return {"mode_score": best_maj - best_min,
            "key": f"{names[key]}{'maj' if is_major else 'min'}"}


def f0_p95(y: np.ndarray, sr: int) -> dict:
    """perceptual_features.f0_p95 벤더링 — voiced_frac(mix)만 소비한다."""
    import librosa
    from scipy.signal import medfilt
    f0, vflag, _vprob = librosa.pyin(y, fmin=F0_MIN, fmax=F0_MAX, sr=sr)
    keep = np.isfinite(f0) & vflag
    hz = f0[keep]
    if hz.size < 10:
        return {"f0_p95_hz": np.nan, "f0_p90_hz": np.nan, "f0_med_hz": np.nan,
                "f0_p95_semi": np.nan, "f0_med_semi": np.nan, "voiced_frac": 0.0}
    hz = medfilt(hz, kernel_size=5)
    to_semi = lambda h: 69 + 12 * np.log2(h / 440.0)  # noqa: E731 (원본 유지)
    return {
        "f0_p95_hz": float(np.percentile(hz, 95)),
        "f0_p90_hz": float(np.percentile(hz, 90)),
        "f0_med_hz": float(np.median(hz)),
        "f0_p95_semi": float(to_semi(np.percentile(hz, 95))),
        "f0_med_semi": float(to_semi(np.median(hz))),
        "voiced_frac": float(keep.mean()),
    }


def r5(x):
    """genre_features_extract.compute.r5 원본 그대로(NaN → 빈 문자열)."""
    return "" if (isinstance(x, float) and x != x) else round(float(x), 5)


def compute_excerpt(y48: np.ndarray, sr48: int) -> dict:
    """genre_features_extract.compute 벤더링 — 원시 특징 dict(r5 반올림)."""
    import librosa
    y22 = librosa.resample(y48, orig_sr=sr48, target_sr=SR) if sr48 != SR else y48
    seg = _center_excerpt(y22, SR, EXCERPT_SEC)

    tb = timbre(seg, SR)
    mv = mode_valence(seg, SR)
    f0 = f0_p95(seg, SR)

    H, P = librosa.effects.hpss(seg)
    harmonic_ratio = float((H ** 2).sum() / ((H ** 2).sum() + (P ** 2).sum() + 1e-9))

    return {
        "harmonic_ratio": r5(harmonic_ratio),
        "centroid": r5(tb["centroid"]), "rolloff": r5(tb["rolloff"]),
        "flatness": r5(tb["flatness"]), "contrast": r5(tb["contrast"]),
        "flux": r5(tb["flux"]), "zcr": r5(tb["zcr"]), "rms": r5(tb["rms"]),
        "tempo_excerpt": r5(tb["tempo"]),
        "mode_score": r5(mv["mode_score"]), "key": mv["key"],
        "voiced_frac_mix": r5(f0["voiced_frac"]),
    }


def extract_from_wav(path: Path) -> dict:
    """wav 파일 1개 → 원시 특징 dict(RAW_FIELDS). genre_features_extract 본문 로드
    관례(soundfile float32, 다채널 평균, duration_s 소수 1자리)를 그대로 따른다."""
    import soundfile as sf
    y48, sr48 = sf.read(str(path), dtype="float32")
    if y48.ndim > 1:
        y48 = y48.mean(axis=1)
    rec = {"duration_s": round(len(y48) / sr48, 1)}
    rec.update(compute_excerpt(y48, sr48))
    return rec
