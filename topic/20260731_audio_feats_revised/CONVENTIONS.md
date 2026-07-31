# 구현 공통 규약 (모든 method-N 스크립트 적용)

> 각 `method-N-*/SPEC.md`는 이 문서를 전제로 한다. 여기 규약과 SPEC.md가 충돌하면 SPEC.md가
> 우선(피처별 예외).

## 경로

```python
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent          # method-N-*/src/
_METHOD_DIR = _THIS_DIR.parent                        # method-N-*/
_TOPIC_DIR = _METHOD_DIR.parent                        # topic/20260731_audio_feats_revised/
_REPO_ROOT = _TOPIC_DIR.parents[1]                      # bpm-research/
_MYPROJECTS_ROOT = _REPO_ROOT.parent                    # pyworks/

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"

AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
)
# 파일명: f"{band}__{idx:03d}.wav"  (예: afterglow__000.wav) — 743개 존재(전곡, 저작물)

VOCAL_STEM_DIR = (
    _MYPROJECTS_ROOT / "bandori-playlist-maker" / "topic" / "mfcc_analysis" / "stems" / "htdemucs"
)
# 폴더명: f"{band}__{idx:03d}/"  하위에 vocals.wav, no_vocals.wav
# ⚠️ 661곡 중 30곡분만 존재(밴드당 3곡, idx 예: afterglow__000/001/002 등). 나머지는 스킵.
```

- `songs_master.csv`는 idx, band, song 등 컬럼 포함(662행=헤더+661곡). 이 파일이 곡 목록의
  단일 진처(source of truth).
- **오디오 파일은 저작물 → 읽기 전용.** 절대 이동/삭제/커밋하지 않는다.

## 출력

- 각 method 폴더 하위 `out/` 디렉터리에 CSV 1개: `out/<feature>_raw.csv`.
- 공통 선두 컬럼: `idx, band, song, duration_sec, ..., error`.
- **동적/스칼라 시계열이 나오는 피처**(energy, valence, danceability, acousticness,
  instrumentalness, liveness, speechiness — loudness는 자체 규약)는 요약통계 4종
  `..._median, ..._p10, ..._p90, ..._std`를 접미사로 통일 산출.
- key/mode/tempo는 이 규약 예외(SPEC.md에 개별 스키마 명시).
- **원시 시계열도 별도 보존**: `out/timeseries/<idx>_<feature>.npy` 등으로 저장(재추론 없이
  재집계 가능하도록). 저장 방식은 SPEC.md에 명시.

## 스크립트 구조 (extract_full_energy.py 관례 준용)

`bandori-playlist-maker/src/scripts/data/extract_full_energy.py`를 참조 구현으로 삼는다.
필수 요소:

1. `extract_features(path: Path, ...) -> dict[str, float]` — 단일 곡 처리 함수(핵심 로직).
2. `_worker(task) -> dict` — 예외를 잡아 `error` 필드에 담고 프로세스를 죽이지 않음(개별 곡
   실패가 전체 배치를 막지 않도록 격리).
3. **Resume 지원**: 이미 `out/<feature>_raw.csv`에 정상 기록된 idx는 재실행 시 스킵.
4. **CLI 인자** (argparse):
   - `--workers N` (기본 4~8, 모델 로딩 비용 있는 피처는 낮게)
   - `--limit N` (테스트용, 앞 N곡만)
   - `--idx 1,2,3` (특정 idx만, 재추출)
   - `--fresh` (기존 출력 무시하고 새로 시작)
5. 진행 로그: 10곡마다 `진행 i/N ok=.. err=.. rate.. ETA..` 형식 출력.
6. `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` — 인코딩 안전.
7. 오디오 로드 실패·모델 추론 실패는 전부 개별 곡 error로 기록하고 계속 진행.

## 실행 환경 표기

각 SPEC.md 상단에 다음 중 하나를 명시한다:
- **네이티브(Windows Python 가능)**: librosa/numpy/scipy/pyloudnorm/torch 기반. 이 저장소
  파이썬 환경(3.13, librosa 0.11, torch 2.12 설치됨)에서 바로 실행·검증 가능.
- **WSL2 필요**: essentia/essentia-tensorflow/madmom 의존. 이 환경엔 WSL2가 아직 구축되지
  않아 **지금은 실행할 수 없다** — 코드는 작성하되, 실행 검증은 WSL2 구축 이후로 미룬다.
  구현자는 해당 라이브러리 API를 정확히 알 수 없을 수 있으므로, import 실패 시에도 스크립트
  전체가 죽지 않도록 모듈 최상단에서 명확한 안내 메시지와 함께 조기 종료(또는 --dry-run으로
  로직만 점검 가능한 경로)를 제공한다.

## 하지 않는 것 (이번 라운드 범위 밖)

- GT 라벨 수집·캘리브레이션·대표 스칼라 최종 선택(energy/valence) — 별도 후속 스크립트.
  이번 라운드는 **원시 추론 + 요약통계 산출까지만**.
- `songs_master.csv` 병합 — 각 피처가 독립적으로 검증된 뒤 별도로 진행.
