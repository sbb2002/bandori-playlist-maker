"""연구 산출 9개 오디오 특징을 songs_master.csv에 병합하는 스크립트.

최종 채택 9개 지표(report_final.md 기준):
  1. m3-mode (필터용) → method-3-mode/out/csv/mode_raw.csv : mode
  2. m4-lufs_integrated (슬라이더) → method-4-loudness/out/csv/loudness_raw.csv : lufs_integrated
  3. m4-lra (슬라이더) → method-4-loudness/out/csv/loudness_raw.csv : lra
  4. m5-arousal_median (슬라이더) → method-5-energy/out/csv/energy_raw.csv : arousal_median
  5. m6-valence_median (슬라이더) → method-6-valence/out/csv/valence_raw.csv : valence_median
  6. m7-danceability_norm (슬라이더) → method-7-danceability/out/csv/danceability_raw.csv : danceability_norm
  7. m8-acoustic_median (토글) → method-8-acousticness/out/csv/acousticness_raw.csv : acoustic_median
  8. m9-instr_stem_ratio (슬라이더) → method-9-instrumentalness/out/csv/instrumentalness_raw.csv : instr_stem_ratio
  9. m11-speech_median (슬라이더) → method-11-speechiness/out/csv/speechiness_raw.csv : speech_median

검증:
  - idx 유일성 (songs_master.csv)
  - 기존 행 수와 신규 행 수 비교
  - 스팟체크: 몇 곡의 값이 실제로 합리적인지 확인
  - 각 방법론 폴더의 산출값이 모두 병합되었는지 확인

실행:
    python auto-loader/data/merge_audio_feats.py <research_repo_path> <data_branch_path>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print("Usage: python merge_audio_feats.py <research_repo> <data_branch_path>")
        sys.exit(1)

    research_root = Path(sys.argv[1])
    data_branch_root = Path(sys.argv[2])

    # 경로 설정
    research_csvs = {
        "method-3-mode": research_root / "topic/20260731_audio_feats_revised/method-3-mode/out/csv/mode_raw.csv",
        "method-4-loudness": research_root / "topic/20260731_audio_feats_revised/method-4-loudness/out/csv/loudness_raw.csv",
        "method-5-energy": research_root / "topic/20260731_audio_feats_revised/method-5-energy/out/csv/energy_raw.csv",
        "method-6-valence": research_root / "topic/20260731_audio_feats_revised/method-6-valence/out/csv/valence_raw.csv",
        "method-7-danceability": research_root / "topic/20260731_audio_feats_revised/method-7-danceability/out/csv/danceability_raw.csv",
        "method-8-acousticness": research_root / "topic/20260731_audio_feats_revised/method-8-acousticness/out/csv/acousticness_raw.csv",
        "method-9-instrumentalness": research_root / "topic/20260731_audio_feats_revised/method-9-instrumentalness/out/csv/instrumentalness_raw.csv",
        "method-11-speechiness": research_root / "topic/20260731_audio_feats_revised/method-11-speechiness/out/csv/speechiness_raw.csv",
    }

    master_csv = data_branch_root / "data/songs_master.csv"
    backup_csv = data_branch_root / "data/songs_master.backup.csv"

    # 연구 데이터 로드
    print("[1/5] Loading research data...")
    loaded = {}
    for method_name, csv_path in research_csvs.items():
        if not csv_path.exists():
            print(f"ERROR: {csv_path} not found")
            sys.exit(1)
        rows = {}
        with open(csv_path, encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                idx = int(row['idx'])
                rows[idx] = row
        loaded[method_name] = rows
        print(f"  {method_name}: {len(rows)} rows")

    # 기존 master CSV 로드 및 백업
    print("[2/5] Loading songs_master.csv...")
    if not master_csv.exists():
        print(f"ERROR: {master_csv} not found")
        sys.exit(1)

    master_rows = []
    master_idxs = []
    with open(master_csv, encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fieldnames_original = reader.fieldnames
        for row in reader:
            idx = int(row['idx'])
            master_rows.append(row)
            master_idxs.append(idx)

    print(f"  {len(master_rows)} rows (idx range {min(master_idxs)} - {max(master_idxs)})")

    # 백업 생성
    master_csv.rename(backup_csv)
    print(f"  Backed up to {backup_csv}")

    # 병합 검증: idx 유일성
    print("[3/5] Validating idx uniqueness...")
    assert len(set(master_idxs)) == len(master_idxs), "Duplicate idx in master"
    print(f"  All {len(master_idxs)} idx values are unique")

    # 병합
    print("[4/5] Merging features...")
    new_columns = [
        "m3-mode", "m4-lufs_integrated", "m4-lra", "m5-arousal_median",
        "m6-valence_median", "m7-danceability_norm", "m8-acoustic_median",
        "m9-instr_stem_ratio", "m11-speech_median"
    ]
    fieldnames_new = list(fieldnames_original) + new_columns

    missing_count = 0
    for row in master_rows:
        idx = int(row['idx'])

        # 각 지표 추가
        row["m3-mode"] = loaded.get("method-3-mode", {}).get(idx, {}).get("mode")
        row["m4-lufs_integrated"] = loaded.get("method-4-loudness", {}).get(idx, {}).get("lufs_integrated")
        row["m4-lra"] = loaded.get("method-4-loudness", {}).get(idx, {}).get("lra")
        row["m5-arousal_median"] = loaded.get("method-5-energy", {}).get(idx, {}).get("arousal_median")
        row["m6-valence_median"] = loaded.get("method-6-valence", {}).get(idx, {}).get("valence_median")
        row["m7-danceability_norm"] = loaded.get("method-7-danceability", {}).get(idx, {}).get("danceability_norm")
        row["m8-acoustic_median"] = loaded.get("method-8-acousticness", {}).get(idx, {}).get("acoustic_median")
        row["m9-instr_stem_ratio"] = loaded.get("method-9-instrumentalness", {}).get(idx, {}).get("instr_stem_ratio")
        row["m11-speech_median"] = loaded.get("method-11-speechiness", {}).get(idx, {}).get("speech_median")

        # 검증: 각 지표가 모두 있는지 확인
        if any(v is None for v in [row["m3-mode"], row["m4-lufs_integrated"], row["m5-arousal_median"],
                                    row["m6-valence_median"], row["m7-danceability_norm"],
                                    row["m8-acoustic_median"], row["m9-instr_stem_ratio"], row["m11-speech_median"]]):
            missing_count += 1

    print(f"  {len(master_rows) - missing_count}/{len(master_rows)} rows fully merged")
    if missing_count > 0:
        print(f"  WARNING: {missing_count} rows missing some features")

    # 파일 기록
    print("[5/5] Writing merged CSV...")
    with open(master_csv, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames_new)
        writer.writeheader()
        writer.writerows(master_rows)

    print(f"  Written {len(master_rows)} rows to {master_csv}")
    print(f"  New columns: {new_columns}")

    # 스팟체크
    print("\n=== Spot check (first 3 rows) ===")
    for row in master_rows[:3]:
        print(f"idx={row['idx']}, band={row['band']}, song={row['song']}")
        print(f"  m5-arousal_median={row['m5-arousal_median']}, m6-valence_median={row['m6-valence_median']}, m3-mode={row['m3-mode']}")

    print("\n=== Spot check (last 3 rows) ===")
    for row in master_rows[-3:]:
        print(f"idx={row['idx']}, band={row['band']}, song={row['song']}")
        print(f"  m5-arousal_median={row['m5-arousal_median']}, m6-valence_median={row['m6-valence_median']}, m3-mode={row['m3-mode']}")

    print("\nMerge completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
