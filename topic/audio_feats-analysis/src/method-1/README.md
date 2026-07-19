# Method 1: Audio Features Extraction (MFCC, LUFS, Chord Progression)

## What This Method Does

This method extracts three categories of audio features from all 661 Bandori songs using librosa and pyloudnorm:

1. **MFCC (Mel-Frequency Cepstral Coefficients)**: 13 coefficients with mean and std (26 total features) capturing spectral characteristics of vocals and instruments.
2. **LUFS (Loudness Units relative to Full Scale)**: Integrated loudness normalization metric for each song.
3. **Chord Progression Derived Features**: Beat-aligned chord detection, key estimation, and derived metrics (pct_major, chord_change_rate, borrowed_chord_rate).

## How It Was Run

Execute from this directory:
```bash
python extract_features.py
```

The script is **idempotent** — progress is tracked in `progress.json`, so interrupted runs can resume without reprocessing. All 661 songs were processed in ~1011 seconds (~17 minutes, avg 1.53 sec/song), with all succeeding (0 errors, 0 skips).

The output CSV also merges existing features from `data/songs_master.csv`, `data/full_audio_features.csv`, and `data/song_features_with_proxies.csv` via **idx (global 0-661 song index) key matching** (not band+song text, which caused 1:N matches on duplicate titles like "R・I・O・T" and "Neo-Aspect"). This ensures 1:1 merge with final 661 rows and 103 total columns (36 new + 67 existing features).
