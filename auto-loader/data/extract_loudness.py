"""Simplified loudness extraction for autoloader — LUFS Integrated + LRA only.

Uses pyloudnorm library (lightweight pure Python, no heavy dependencies).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def extract_features(path: Path) -> dict[str, float]:
    """Extract loudness features from a single audio file.

    Args:
        path: Path to audio file (wav)

    Returns:
        dict with keys: lufs_integrated, lra (both raw dB values, not normalized)

    Note:
        Returns float('nan') if extraction fails for a specific metric.
    """
    import pyloudnorm as pyln
    import soundfile as sf

    # Load audio
    data, sr = sf.read(str(path), dtype=np.float32)

    # Convert stereo to mono if needed
    if data.ndim == 2:
        data = data.mean(axis=1)

    # Integrated loudness
    meter = pyln.Meter(sr)
    lufs_integrated = meter.integrated_loudness(data)
    if lufs_integrated is None:
        lufs_integrated = float("nan")
    else:
        lufs_integrated = float(lufs_integrated)

    # Short-term loudness time series for LRA (Loudness Range)
    lra = _compute_lra(data, sr)

    return {
        "lufs_integrated": lufs_integrated,
        "lra": lra,
    }


def _compute_lra(data: np.ndarray, sr: int, window_sec: float = 3.0) -> float:
    """Compute EBU R128 Loudness Range (LRA = P90 - P10 of short-term loudness).

    Args:
        data: Mono audio array
        sr: Sample rate
        window_sec: Window length in seconds (default 3.0)

    Returns:
        float: LRA value in dB, or float('nan') if insufficient data
    """
    import pyloudnorm as pyln

    meter = pyln.Meter(sr)
    window_samples = int(window_sec * sr)
    hop_samples = window_samples // 2  # 50% overlap

    loudness_values = []

    # Sliding window calculation
    for start in range(0, len(data) - window_samples + 1, hop_samples):
        frame = data[start : start + window_samples]
        try:
            loudness = meter.integrated_loudness(frame)
            # Absolute gating: exclude frames below -70 LUFS
            if loudness is not None and loudness > -70:
                loudness_values.append(loudness)
        except (ValueError, RuntimeError):
            # Skip frames that are too short or silent
            continue

    if len(loudness_values) < 2:
        return float("nan")

    loudness_array = np.array(loudness_values, dtype=np.float32)
    p10 = float(np.percentile(loudness_array, 10))
    p90 = float(np.percentile(loudness_array, 90))
    lra = p90 - p10

    return lra
