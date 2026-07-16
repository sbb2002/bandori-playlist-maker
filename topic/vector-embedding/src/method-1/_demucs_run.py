"""Environment shim — this torchaudio build hard-requires torchcodec for
`torchaudio.load`, and demucs.separate only catches RuntimeError around
that call (not torchcodec's ImportError/OSError), so `python -m demucs`
crashes outright. Patch `torchaudio.load` to read via soundfile instead,
then invoke demucs.separate in-process so the patch takes effect.

Usage: python _demucs_run.py -n htdemucs --two-stems vocals -o <out> <src>
"""
import sys
import numpy as np
import soundfile as sf
import torch
import torchaudio


def _load_via_soundfile(path, *a, **kw):
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    wav = torch.from_numpy(np.ascontiguousarray(data.T))
    return wav, sr


def _save_via_soundfile(path, src, sample_rate, *a, **kw):
    data = src.detach().cpu().numpy().T
    sf.write(str(path), data, sample_rate)


torchaudio.load = _load_via_soundfile
torchaudio.save = _save_via_soundfile

from demucs.separate import main  # noqa: E402 — must import after the patch

if __name__ == "__main__":
    main(sys.argv[1:])
