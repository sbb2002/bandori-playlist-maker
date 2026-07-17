"""Configuration for chord progression analysis pilot.

DESIGN.md §6: Constants and paths.
"""
import os
from pathlib import Path
import numpy as np

# Base paths
_SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = _SCRIPT_DIR.parent.parent

# SEED: inherited from DESIGN.md §6 (20260717)
SEED = 20260717

# Input data paths
GROUND_TRUTH_LABELS = PROJECT_ROOT / "data" / "ground_truth_labels.csv"
SONGS_MASTER = PROJECT_ROOT / "data" / "songs_master.csv"
FULL_CATALOG = PROJECT_ROOT / "topic" / "vector-embedding" / "src" / "method-1" / "full_catalog_songs.csv"

# Stems path: DESIGN.md §1
STEMS_BASE = PROJECT_ROOT / "topic" / "vector-embedding" / "src" / "method-1" / "work" / "stems_full" / "htdemucs"

# Output directory
OUT_DIR = _SCRIPT_DIR / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# DESIGN.md §3: 24-chord template profiles (major + minor triads)
# Binary profiles: root, major-3rd, perfect-5th = 1, others = 0
# Chromagram indices: C=0, C#=1, D=2, D#=3, E=4, F=5, F#=6, G=7, G#=8, A=9, A#=10, B=11
# ============================================================================

def _make_chord_template(root: int, is_major: bool) -> np.ndarray:
    """
    Create a 12-dimensional binary chord template.

    Args:
        root: Root note index (0-11, C=0)
        is_major: True for major, False for minor

    Returns:
        12D binary template [root, major3rd/minor3rd, perfect5th]
    """
    template = np.zeros(12)
    template[root % 12] = 1  # root
    template[(root + (4 if is_major else 3)) % 12] = 1  # 3rd
    template[(root + 7) % 12] = 1  # perfect 5th
    return template


# Major chords (C, C#, D, ..., B)
MAJOR_TEMPLATES = {
    "Cmaj": _make_chord_template(0, True),
    "C#maj": _make_chord_template(1, True),
    "Dmaj": _make_chord_template(2, True),
    "D#maj": _make_chord_template(3, True),
    "Emaj": _make_chord_template(4, True),
    "Fmaj": _make_chord_template(5, True),
    "F#maj": _make_chord_template(6, True),
    "Gmaj": _make_chord_template(7, True),
    "G#maj": _make_chord_template(8, True),
    "Amaj": _make_chord_template(9, True),
    "A#maj": _make_chord_template(10, True),
    "Bmaj": _make_chord_template(11, True),
}

# Minor chords
MINOR_TEMPLATES = {
    "Cmin": _make_chord_template(0, False),
    "C#min": _make_chord_template(1, False),
    "Dmin": _make_chord_template(2, False),
    "D#min": _make_chord_template(3, False),
    "Emin": _make_chord_template(4, False),
    "Fmin": _make_chord_template(5, False),
    "F#min": _make_chord_template(6, False),
    "Gmin": _make_chord_template(7, False),
    "G#min": _make_chord_template(8, False),
    "Amin": _make_chord_template(9, False),
    "A#min": _make_chord_template(10, False),
    "Bmin": _make_chord_template(11, False),
}

# All 24 templates
ALL_CHORD_TEMPLATES = {**MAJOR_TEMPLATES, **MINOR_TEMPLATES}

# Pitch class names for reference (for Krumhansl-Schmuckler key estimation)
PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler (K-S) profiles for key estimation
# These are empirically-derived chroma profiles that indicate likelihood of each key
# Reference: Krumhansl, C. L. (1990). Cognitive Foundations of Musical Pitch.
# Implementation: correlation of mean chroma with these reference profiles
# This is a well-known standard in music information retrieval.

# Major/minor key profiles (Krumhansl & Kessler 1982)
#
# BUGFIX (code review): the previous arrays were NOT the actual published
# Krumhansl-Kessler profile values, despite the comment claiming so. They
# were a fabricated binary-ish pattern (in-scale degrees all = 3.48,
# out-of-scale degrees all = 2.33), which loses the tonal-hierarchy
# information (tonic/dominant/mediant emphasis) that the real K-S algorithm
# relies on to disambiguate keys. Replaced with the actual published values
# (see e.g. Krumhansl 1990, Table 2; Temperley 1999) that are the de facto
# standard used across MIR key-finding implementations (music21, librosa
# examples, etc.).
_KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KS_MAJOR = _KS_MAJOR / np.sum(_KS_MAJOR)

_KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_KS_MINOR = _KS_MINOR / np.sum(_KS_MINOR)

# Store all 24 key profiles (12 major + 12 minor)
KS_PROFILES = {}
for pc_idx, pc in enumerate(PITCH_CLASSES):
    # Rotate major profile to align with this pitch class as tonic
    rotated_major = np.roll(_KS_MAJOR, -pc_idx)
    rotated_minor = np.roll(_KS_MINOR, -pc_idx)
    KS_PROFILES[f"{pc}maj"] = rotated_major
    KS_PROFILES[f"{pc}min"] = rotated_minor


# ============================================================================
# Diatonic chord pool (DESIGN.md §4)
# For borrowed_chord_rate: which 7 chords are diatonic in each major/minor key
# ============================================================================

def _get_diatonic_chords(root: int, is_major: bool) -> set:
    """
    Return the (root, quality) pairs of diatonic triads in a key.

    For major: I(maj), ii(min), iii(min), IV(maj), V(maj), vi(min), vii°(dim)
    For minor (natural): i(min), ii°(dim), III(maj), iv(min), v(min), VI(maj), VII(maj)

    BUGFIX (code review): the original implementation returned only the *root
    pitch classes* of the diatonic scale degrees, and 03_compute_features.py
    checked membership using the chord root alone, ignoring quality. Since the
    recognizer (02_extract_chords.py / config.ALL_CHORD_TEMPLATES) only has
    24 major/minor triad templates (no diminished template), a chord is
    always assigned maj or min. Root-only membership meant a "borrowed"
    same-root-different-quality chord (e.g. tonic major borrowed into a minor
    key: Picardy third / modal mixture, or a major V borrowed into a minor
    key that normally has a minor v) would NOT be flagged as borrowed, even
    though this is *exactly* the J-rock phenomenon borrowed_chord_rate is
    designed to detect (DESIGN.md §4: "단조 진행이라도 장조 색채 코드를 섞어
    밝게 들리게 하는 경우"). Fixed by keying diatonicity on (root, quality)
    pairs. The diminished scale degrees (vii° in major, ii° in minor) have no
    matching template; they are approximated as "min" (a diminished triad
    shares root+minor-3rd with a minor triad, differing only in the 5th,
    so it is the closer of the two available templates).

    Args:
        root: Root note (0-11)
        is_major: True for major, False for minor (natural)

    Returns:
        Set of (root_index, quality) tuples, quality in {"maj", "min"}
    """
    if is_major:
        # (semitone interval from root, quality) for I, ii, iii, IV, V, vi, vii°
        scale_degrees = [
            (0, "maj"), (2, "min"), (4, "min"), (5, "maj"),
            (7, "maj"), (9, "min"), (11, "min"),  # vii° approximated as min
        ]
    else:
        # (semitone interval from root, quality) for i, ii°, III, iv, v, VI, VII
        scale_degrees = [
            (0, "min"), (2, "min"), (3, "maj"), (5, "min"),
            (7, "min"), (8, "maj"), (10, "maj"),  # ii° approximated as min
        ]

    return {((root + interval) % 12, quality) for interval, quality in scale_degrees}


# Store diatonic pools for all 24 keys
DIATONIC_POOLS = {}
for pc_idx, pc in enumerate(PITCH_CLASSES):
    for quality in ["maj", "min"]:
        is_major = (quality == "maj")
        key_name = f"{pc}{quality}"
        DIATONIC_POOLS[key_name] = _get_diatonic_chords(pc_idx, is_major)
