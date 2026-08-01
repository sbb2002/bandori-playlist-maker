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
# 파일명: f"{band}__{file_idx:03d}.wav"  (예: afterglow__000.wav) — 743개 존재(전곡, 저작물)
# ⚠️ 2026-08-01부로 idx != file_idx. 반드시 songs_master.csv의 file_idx 컬럼으로 파일을 찾을 것.
# 아래 "idx와 file_idx" 절 참고.

VOCAL_STEM_DIR = (
    _MYPROJECTS_ROOT / "bandori-playlist-maker" / "topic" / "mfcc_analysis" / "stems" / "htdemucs"
)
# 폴더명: f"{band}__{idx:03d}/"  하위에 vocals.wav, no_vocals.wav
# ⚠️ 661곡 중 30곡분만 존재(밴드당 3곡, idx 예: afterglow__000/001/002 등). 나머지는 스킵.
```

- `songs_master.csv`는 idx, band, song, file_idx 등 컬럼 포함(737행=헤더+736곡, 2026-08-01
  기준). 이 파일이 곡 목록의 단일 진처(source of truth).
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


## idx와 file_idx (2026-08-01 구조 개선 — 재발 방지 필독)

**배경**: 초기 661곡(idx 0~662, 2개 결번 525·588 포함)은 idx가 곧 오디오 파일명 번호였다.
이후 형제 프로젝트(bandori-song-sorter)의 `audio_full/` 폴더에 새로 생긴 75곡을 `songs_master.csv`에
병합하면서, 이 75곡의 idx를 오디오 파일명 번호에서 그대로 가져왔더니 **다른 밴드의 기존 idx와
48건 충돌**했다(예: `mugendai_mutype__263.wav`와 기존 `mygo__263.wav`가 둘 다 idx=263). 이를 계기로
idx의 의미를 아래와 같이 재정의했다.

- **`idx`는 이 연구 저장소가 관리하는 전역 유일(global unique) synthetic key다.**
  오디오 파일명 번호와 절대 동일하다고 가정하지 말 것.
- **`file_idx`는 실제 오디오 파일명(`{band}__{file_idx:03d}.wav`)의 번호**이며, **밴드 내에서만**
  유일함이 보장된다(전역 유일 아님 — 다른 밴드가 같은 file_idx를 쓸 수 있다).
- 오디오 파일(및 `VOCAL_STEM_DIR`의 스템 폴더 `{band}__{file_idx:03d}/`)을 찾을 때는 반드시
  `file_idx`를 써야 한다. `idx`로 파일명을 조립하면 틀린 파일을 열거나(다른 밴드 곡과 충돌),
  파일이 아예 없을 수 있다.
- 2026-08-01 기준 매핑 결과: 원래 661곡(idx 0~662, 2개 결번)은 `file_idx == idx`(그대로).
  신규 75곡은 idx 663~737을 새로 순차 부여받았고, `file_idx`에는 원래 갖고 있던(=오디오
  파일명 그대로의) 값을 보존했다. 즉 idx 전체 범위는 0~737(525·588 결번, 736곡)이며 완전히
  유일하다.
- 각 method의 `_audio_path()`/`stem_paths()` 계열 함수는 모두 `file_idx`를 인자로 받도록
  고쳐져 있다(`songs_master.csv`의 `r["file_idx"]`를 읽어 전달). 새 추출 스크립트를 작성할
  때도 이 규칙을 반드시 따를 것 — `r["idx"]`를 오디오 경로 조립에 직접 쓰지 말 것.

### 신곡 추가 절차(권장)

앞으로 신곡을 `songs_master.csv`에 추가할 때는:

1. 새 idx는 반드시 `max(기존 idx) + 1`부터 순차 부여한다. 오디오 파일명 번호를 그대로
   idx로 쓰지 않는다.
2. `file_idx`에는 실제 오디오 파일명(`{band}__{file_idx:03d}.wav`)의 번호를 그대로 기록한다.
3. 추가 전 다음을 검증한다(간단한 assert 또는 체크 스크립트 권장):
   - 새로 부여하려는 idx 값들이 기존 `idx` 컬럼과 전혀 겹치지 않는가(전역 유일성).
   - 신규 행의 `(band, file_idx)` 조합이 같은 밴드 내에서 기존 행과 겹치지 않는가
     (동일 곡 중복 추가 방지).
4. 기존 out/*_raw.csv·timeseries 파일은 건드리지 않는다 — 신규 곡 분만 추가로 추출한다.
