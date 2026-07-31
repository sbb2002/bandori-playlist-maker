"""method-2-key/out/key_raw.csv를 읽어 mode 신뢰도 리포트를 만든다.
오디오를 새로 열지 않는다 — key 산출의 부산물이라는 설계를 코드로도 강제.

out/mode_raw.csv: idx, band, song, mode (major/minor)
out/mode_report.md: mode_only_mismatch 비율 요약 및 불일치 사례
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, OSError):
    pass


def _setup_paths():
    """경로 설정 (CONVENTIONS.md 준용, 단 오디오 경로는 import하지 않음)"""
    THIS_DIR = Path(__file__).resolve().parent  # method-3-mode/src/
    METHOD_DIR = THIS_DIR.parent                 # method-3-mode/
    TOPIC_DIR = METHOD_DIR.parent                # topic/20260731_audio_feats_revised/
    REPO_ROOT = TOPIC_DIR.parents[1]             # bpm-research/

    # method-2-key와 method-3-mode는 같은 TOPIC_DIR 아래의 형제 디렉터리
    KEY_RAW_CSV = TOPIC_DIR / "method-2-key" / "out" / "key_raw.csv"
    MODE_OUT_DIR = METHOD_DIR / "out"
    MODE_RAW_CSV = MODE_OUT_DIR / "mode_raw.csv"
    MODE_REPORT_MD = MODE_OUT_DIR / "mode_report.md"

    return {
        "THIS_DIR": THIS_DIR,
        "METHOD_DIR": METHOD_DIR,
        "TOPIC_DIR": TOPIC_DIR,
        "REPO_ROOT": REPO_ROOT,
        "KEY_RAW_CSV": KEY_RAW_CSV,
        "MODE_OUT_DIR": MODE_OUT_DIR,
        "MODE_RAW_CSV": MODE_RAW_CSV,
        "MODE_REPORT_MD": MODE_REPORT_MD,
    }


def load_key_raw_csv(key_raw_path: Path) -> pd.DataFrame:
    """key_raw.csv 로드. 파일 없으면 명확한 에러로 종료."""
    if not key_raw_path.exists():
        error_msg = f"""먼저 method-2-key를 실행하세요: {key_raw_path} 없음

method-2-key의 extract_key_ks.py를 먼저 실행하여 key_raw.csv를 생성해야 합니다."""
        print(error_msg, file=sys.stderr)
        sys.exit(1)

    try:
        df = pd.read_csv(key_raw_path, dtype={"idx": int, "band": str, "song": str})
        # extract_key_ks.py는 --idx 재추출 시 중복 idx를 append할 수 있다(관례상 "build
        # 단계에서 최신 우선 처리" — 이 스크립트가 그 build 단계) → idx당 마지막 행만 채택.
        df = df.drop_duplicates(subset="idx", keep="last").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"key_raw.csv 읽기 실패: {e}", file=sys.stderr)
        sys.exit(1)


def build_mode_raw_csv(df_key: pd.DataFrame, output_path: Path):
    """mode_raw.csv 생성: idx, band, song, mode"""
    # mode_ks 컬럼을 mode로 rename하여 저장
    required_cols = {"idx", "band", "song", "mode_ks"}
    if not required_cols.issubset(df_key.columns):
        missing = required_cols - set(df_key.columns)
        print(f"key_raw.csv에 필수 컬럼이 없습니다: {missing}", file=sys.stderr)
        sys.exit(1)

    df_mode = df_key[["idx", "band", "song", "mode_ks"]].copy()
    df_mode.rename(columns={"mode_ks": "mode"}, inplace=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_mode.to_csv(output_path, index=False, encoding="utf-8")
    print(f"mode_raw.csv 생성 완료: {output_path} ({len(df_mode)}행)")


def build_mode_report(df_key: pd.DataFrame, output_path: Path):
    """mode_report.md 생성: mode_only_mismatch 비율 및 불일치 사례"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # mode_only_mismatch 컬럼이 있는 행만 대상(essentia 교차검증이 채워진 행)
    if "mode_only_mismatch" not in df_key.columns:
        # 아직 essentia 교차검증이 완료되지 않은 경우
        report_content = f"""# mode 신뢰도 리포트

**생성일**: {datetime.now().isoformat()}

## 상태

Essentia 교차검증 대기 중:
- method-2-key의 `extract_key_essentia.py` (WSL2)가 아직 완료되지 않았습니다.
- 현재는 K-S 다수결 mode_ks 값만 출력됩니다.
- Essentia 교차검증 완료 후 `mode_only_mismatch` 비율이 계산됩니다.

## 곡수

- 총 곡수: {len(df_key)}
"""
    else:
        # essentia 교차검증이 있는 행만 대상
        df_with_essentia = df_key[df_key["mode_only_mismatch"].notna()].copy()

        if len(df_with_essentia) == 0:
            report_content = f"""# mode 신뢰도 리포트

**생성일**: {datetime.now().isoformat()}

## 상태

Essentia 교차검증 결과 없음:
- key_raw.csv에 mode_only_mismatch 값이 채워지지 않았습니다.
- WSL2 환경에서 extract_key_essentia.py를 실행해야 합니다.
"""
        else:
            # mode_only_mismatch 비율 계산
            mode_mismatch_count = df_with_essentia["mode_only_mismatch"].sum()
            mode_mismatch_ratio = mode_mismatch_count / len(df_with_essentia)

            # 불일치 곡 목록 (상위 20곡)
            mismatch_songs = df_with_essentia[df_with_essentia["mode_only_mismatch"] == True].copy()
            mismatch_songs = mismatch_songs[["idx", "band", "song", "key_ks", "mode_ks", "key_essentia", "mode_essentia"]]

            # 리포트 작성
            report_content = f"""# mode 신뢰도 리포트

**생성일**: {datetime.now().isoformat()}

## 요약

- 검증 대상 곡수: {len(df_with_essentia)}
- **mode 불일치 (모드만 불일치)**: {mode_mismatch_count}곡 ({mode_mismatch_ratio*100:.1f}%)
- K-S 다수결 기준 mode_ks 신뢰도: {(1-mode_mismatch_ratio)*100:.1f}%

## 모드만 불일치한 곡 (청취 스팟체크 대상)

불일치 시 K-S vs Essentia 모드 불일치는 관계조(근접조) 혼동의 신호입니다.
Essentia의 고전적 오류 패턴이 관계장/단조 혼동이므로, 이 목록의 곡들을 청취하여
실제 선곡 맥락에 맞는 mode를 선택해야 합니다.

"""
            if len(mismatch_songs) > 0:
                # 마크다운 테이블 생성 (tabulate 없이)
                report_content += "| idx | band | song | key_ks | mode_ks | key_essentia | mode_essentia |\n"
                report_content += "|-----|------|------|--------|---------|--------------|---------------|\n"
                for _, row in mismatch_songs.iterrows():
                    report_content += f"| {row['idx']} | {row['band']} | {row['song']} | {row['key_ks']} | {row['mode_ks']} | {row['key_essentia']} | {row['mode_essentia']} |\n"
                report_content += "\n"

            # 통계 요약
            report_content += f"""

## 디버깅 정보

- 전체 key_raw.csv 곡수: {len(df_key)}
- Essentia 교차검증 완료 곡수: {len(df_with_essentia)}
- Essentia 미완료 곡수: {len(df_key) - len(df_with_essentia)}
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"mode_report.md 생성 완료: {output_path}")


def main():
    """메인 진입점"""
    paths = _setup_paths()

    print(f"입력: {paths['KEY_RAW_CSV']}")

    # key_raw.csv 로드
    df_key = load_key_raw_csv(paths["KEY_RAW_CSV"])
    print(f"key_raw.csv 로드 완료: {len(df_key)}행")

    # 출력 디렉터리 생성
    paths["MODE_OUT_DIR"].mkdir(parents=True, exist_ok=True)

    # mode_raw.csv 생성
    build_mode_raw_csv(df_key, paths["MODE_RAW_CSV"])

    # mode_report.md 생성
    build_mode_report(df_key, paths["MODE_REPORT_MD"])

    print("\n완료!")


if __name__ == "__main__":
    main()
