#!/usr/bin/env python3
r"""
병합 스크립트: bandori-song-sorter의 pulse 분석 데이터를 audio_feats.csv에 추가

소스: C:\Users\User\Documents\pyworks\bandori-song-sorter\src\content\cluster\onsets\{tag}.json
목표: audio_feats.csv에 7개 컬럼 추가
  - drum_tempo_bpm: json의 'tempo'
  - pulse_bpm: json의 'pulse.pulse_bpm'
  - pulse_div: json의 'pulse.pulse_div'
  - pulse_ratio: json의 'pulse.ratio'
  - pulse_acf_slow: json의 'pulse.acf_slow'
  - pulse_acf_fast: json의 'pulse.acf_fast'
  - pulse_tau: json의 'pulse.tau'

기존 컬럼(tempo_bpm, bpm 등)은 절대 변경하지 않음.
파일이 없으면 NaN으로 처리.
"""

import json
import pandas as pd
from pathlib import Path
import sys

# 경로 설정
BROTHER_PROJECT_ROOT = Path("C:/Users/User/Documents/pyworks/bandori-song-sorter")
ONSETS_DIR = BROTHER_PROJECT_ROOT / "src/content/cluster/onsets"
CSV_PATH = Path("./out/audio_feats.csv")

def load_pulse_data(tag: str) -> dict:
    """
    주어진 tag에 대해 onsets JSON에서 pulse 데이터를 로드.
    파일이 없으면 모두 NaN 반환.
    """
    json_path = ONSETS_DIR / f"{tag}.json"

    result = {
        "drum_tempo_bpm": None,
        "pulse_bpm": None,
        "pulse_div": None,
        "pulse_ratio": None,
        "pulse_acf_slow": None,
        "pulse_acf_fast": None,
        "pulse_tau": None,
    }

    if not json_path.exists():
        return result

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 최상위 tempo
        result["drum_tempo_bpm"] = data.get("tempo")

        # pulse 객체 하위 값들
        pulse = data.get("pulse", {})
        result["pulse_bpm"] = pulse.get("pulse_bpm")
        result["pulse_div"] = pulse.get("pulse_div")
        result["pulse_ratio"] = pulse.get("ratio")
        result["pulse_acf_slow"] = pulse.get("acf_slow")
        result["pulse_acf_fast"] = pulse.get("acf_fast")
        result["pulse_tau"] = pulse.get("tau")

        return result
    except Exception as e:
        print(f"Warning: Failed to load {json_path}: {e}", file=sys.stderr)
        return result

def main():
    # CSV 읽기
    print(f"Reading {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    print(f"Initial shape: {df.shape}")
    print(f"Columns before merge: {df.shape[1]}")

    # 새 컬럼 초기화 (NaN)
    new_cols = [
        "drum_tempo_bpm",
        "pulse_bpm",
        "pulse_div",
        "pulse_ratio",
        "pulse_acf_slow",
        "pulse_acf_fast",
        "pulse_tau",
    ]

    for col in new_cols:
        df[col] = None

    # tag 별로 pulse 데이터 로드
    print(f"Loading pulse data from {ONSETS_DIR}...")

    for idx, row in df.iterrows():
        tag = row["tag"]
        pulse_data = load_pulse_data(tag)

        for col in new_cols:
            df.at[idx, col] = pulse_data[col]

        if (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{len(df)} rows...")

    # CSV 저장
    print(f"Writing to {CSV_PATH}...")
    df.to_csv(CSV_PATH, index=False)

    print(f"Final shape: {df.shape}")
    print(f"Columns after merge: {df.shape[1]}")
    print("Done!")

if __name__ == "__main__":
    main()
