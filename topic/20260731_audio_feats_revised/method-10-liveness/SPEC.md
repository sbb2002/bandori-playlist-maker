# method-10-liveness 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §10, "분포 퇴화
> 탈출 조건".

## 실행 환경
- **네이티브(Windows Python 가능, 단 신규 패키지 필요)** — PANNs는 essentia가 아니라
  `panns-inference`(pip 설치, torch 기반) 사용 — 이 저장소에 torch 2.12가 이미 설치돼 있어
  **essentia/madmom과 달리 WSL2가 필요 없다**. `pip install panns-inference`만 추가하면 됨
  (사전학습 체크포인트는 최초 실행 시 자동 다운로드 — 실패 시 명확한 에러로 종료).
- 보조(노이즈플로어+RT60)도 librosa/scipy만으로 네이티브 가능.

## 산출물

`out/liveness_raw.csv`:
```
idx, band, song, duration_sec,
crowd_median, crowd_p10, crowd_p90, crowd_std,   # Crowd/Applause/Cheering 평균확률 시계열 요약
noise_floor_db,             # 통계적 보조: 광대역 노이즈플로어(dB)
rt60_est_sec,                # 통계적 보조: 잔향 꼬리 길이 추정(초)
n_patches,
error
```
`out/timeseries/<idx>_crowd.npy`: PANNs 프레임별 확률 시계열.

## `extract_liveness_panns.py`

```python
from panns_inference import AudioTagging, labels  # labels: AudioSet 527 클래스명 리스트

TARGET_LABELS = ["Crowd", "Applause", "Cheering"]  # labels 리스트에서 정확한 표기 확인 후 확정

def load_model():
    # AudioTagging(checkpoint_path=None, device='cuda' if torch.cuda.is_available() else 'cpu')

def extract_features(path: Path, model) -> dict:
    # librosa.load(path, sr=32000, mono=True)  # PANNs 요구 SR=32000
    # framewise_output 반환하는 inference 모드 사용(clipwise 평균이 아니라 프레임별 시계열 필요
    #   — panns_inference의 AudioTagging.inference()는 framewise_output도 함께 반환하는지
    #   API 확인, 없으면 오디오를 수 초 단위로 잘라 clip 단위 반복 추론으로 시계열 구성)
    # TARGET_LABELS 3개 클래스 확률의 프레임별 평균 → crowd_series
    # 요약통계 산출
```
- 오탐 주의(README 명시): 곡 내 함성 이펙트·갱보컬이 오검출될 수 있음 — 이 스크립트는 원시
  확률만 뽑고, 청취 대조는 범위 밖(후속).

## `extract_liveness_stat.py` (통계적 보조, 네이티브)

```python
# noise_floor_db: 트랙 전체에서 RMS 하위 percentile(예 p5) 구간의 dBFS
# rt60_est_sec: 곡 끝부분(마지막 노트 이후) 감쇠 구간의 에너지 감쇠 기울기로 RT60 추정
#   (Schroeder 적분 등 표준 잔향시간 추정법 참고 — 정밀 음향측정용 RT60이 아니라 근사치임을
#   주석으로 명시)
```

## 검증 방법 (내가 수행)
- `panns-inference` 설치 성공 여부부터 확인 필요(`pip install panns-inference`) — 설치되면
  `--limit 3`으로 즉시 실행해 확률값 범위(0~1)와 체크포인트 다운로드 정상 여부 확인.
- 통계적 보조 스크립트는 즉시 네이티브 실행 검증 가능.
