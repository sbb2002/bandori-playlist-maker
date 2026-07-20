from pathlib import Path
import numpy as np

_SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = _SCRIPT_DIR.parent.parent.parent.parent  # topic/audio_feats_analysis/src/method-1 -> repo root

# 형제 프로젝트(bandori-song-sorter)의 원본 오디오. 이 저장소 밖에 있는 별도 로컬 프로젝트다.
AUDIO_DIR = Path("C:/Users/User/Documents/pyworks/bandori-song-sorter/src/content/cluster/audio_full")

# 661곡 tag 목록 (band__idx 형식, audio_full/<tag>.wav 파일명과 일치)
FULL_CATALOG = PROJECT_ROOT / "topic" / "vector_embedding" / "src" / "method-1" / "full_catalog_songs.csv"

OUT_DIR = _SCRIPT_DIR.parent.parent / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _make_chord_template(root, is_major):
    template = np.zeros(12)
    template[root % 12] = 1
    template[(root + (4 if is_major else 3)) % 12] = 1
    template[(root + 7) % 12] = 1
    return template


MAJOR_TEMPLATES = {f"{pc}maj": _make_chord_template(i, True) for i, pc in enumerate(PITCH_CLASSES)}
MINOR_TEMPLATES = {f"{pc}min": _make_chord_template(i, False) for i, pc in enumerate(PITCH_CLASSES)}
ALL_CHORD_TEMPLATES = {**MAJOR_TEMPLATES, **MINOR_TEMPLATES}

_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MAJOR = _KS_MAJOR / np.sum(_KS_MAJOR)
_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_KS_MINOR = _KS_MINOR / np.sum(_KS_MINOR)

KS_PROFILES = {}
for pc_idx, pc in enumerate(PITCH_CLASSES):
    KS_PROFILES[f"{pc}maj"] = np.roll(_KS_MAJOR, -pc_idx)
    KS_PROFILES[f"{pc}min"] = np.roll(_KS_MINOR, -pc_idx)


def _get_diatonic_chords(root, is_major):
    if is_major:
        scale_degrees = [(0, "maj"), (2, "min"), (4, "min"), (5, "maj"), (7, "maj"), (9, "min"), (11, "min")]
    else:
        scale_degrees = [(0, "min"), (2, "min"), (3, "maj"), (5, "min"), (7, "min"), (8, "maj"), (10, "maj")]
    return {((root + interval) % 12, quality) for interval, quality in scale_degrees}


DIATONIC_POOLS = {}
for pc_idx, pc in enumerate(PITCH_CLASSES):
    for quality in ["maj", "min"]:
        DIATONIC_POOLS[f"{pc}{quality}"] = _get_diatonic_chords(pc_idx, quality == "maj")
