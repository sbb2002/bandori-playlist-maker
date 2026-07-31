c# method-1-tempo 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §1.

## 실행 환경
- **네이티브(Windows Python 가능)** — `extract_tempo_librosa.py`: librosa만 사용.
- **WSL2 필요** — `extract_tempo_madmom.py`: madmom(GitHub master) 사용. 이 환경엔 WSL2가
  아직 없으므로 **지금은 실행 불가** — 코드만 작성. 모듈 최상단에서 `import madmom` 실패 시
  `"madmom 미설치 — WSL2 환경에서 실행하세요"` 메시지와 함께 `sys.exit(1)`.

## 산출물 (두 스크립트 모두 같은 파일에 컬럼만 추가)

`out/tempo_raw.csv`:
```
idx, band, song, duration_sec,
bpm_autocorr,                 # librosa 스크립트가 채움
bpm_madmom, beat_count, beat_interval_median_sec, halftime_flag,  # madmom 스크립트가 채움
error
```
- 두 스크립트는 **같은 CSV를 다른 컬럼 세트로 채운다** — 이미 존재하는 행은 idx 기준으로
  업데이트(덮어쓰기 아님, 컬럼만 병합). 없으면 새 행 추가.
- 최종 대표 BPM 결정(둘 중 채택)은 이번 라운드 범위 밖 — 원시값만 남긴다.

## Stage A: `extract_tempo_librosa.py` (1차 후보)

```python
def extract_features(path: Path) -> dict:
    # librosa.load(path, sr=22050, mono=True)
    # onset_env = librosa.onset.onset_strength(y=y, sr=sr)  # 스펙트럴 플럭스
    # tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    # 자기상관 기반 후보: librosa.beat.tempo(onset_envelope=onset_env, sr=sr, aggregate=None)
    #   의 최빈 피크를 bpm_autocorr로 사용(단일 스칼라)
    return {"duration_sec": ..., "bpm_autocorr": float(tempo)}
```
CLI: `--workers 8 --limit --idx --fresh` (CONVENTIONS 표준).

## Stage B: `extract_tempo_madmom.py` (정제, WSL2)

```python
from madmom.features.beats import DBNBeatTrackingProcessor
from madmom.features.beats import RNNBeatProcessor

def extract_features(path: Path, min_bpm: int = 55, max_bpm: int = 320) -> dict:
    # act = RNNBeatProcessor()(str(path))
    # proc = DBNBeatTrackingProcessor(min_bpm=min_bpm, max_bpm=max_bpm, fps=100)
    # beats = proc(act)  # 초 단위 비트 타임스탬프 배열
    # intervals = np.diff(beats)
    # bpm_madmom = 60.0 / np.median(intervals)
    # halftime_flag: intervals의 IQR/median이 임계(예 0.3) 초과 시 True(비트 간격 불안정)
    ...
```
- **기본 madmom 탐지범위(55–215BPM)를 그대로 쓰지 말 것** — `--min-bpm/--max-bpm` CLI 인자
  기본값을 `55`/`320`으로 넓혀 이 카탈로그의 고속곡(215BPM+)을 반절로 접지 않게 한다.
- `beat_count`, `beat_interval_median_sec`도 함께 기록(하프타임 판정 근거로 후속 분석에 사용).

## 검증 방법 (내가 수행)
- Stage A는 이 저장소 파이썬 환경에서 `--limit 5` 등으로 즉시 실행해 값 확인 가능.
- Stage B는 WSL2 구축 전까지 정적 리뷰만(문법·구조·인자 처리 확인). `python -m py_compile`로
  구문 오류만 확인.
