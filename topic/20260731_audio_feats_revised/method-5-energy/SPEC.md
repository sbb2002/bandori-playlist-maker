# method-5-energy 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §5.
> **이번 라운드 범위**: arousal 회귀 원시 추론 + 요약통계 산출까지만. GT 캘리브레이션·대표
> 스칼라 최종 선택은 범위 밖(후속 스크립트).

## 실행 환경
- **WSL2 필요** — essentia-tensorflow의 emoMusic/DEAM arousal 회귀 모델(MusiCNN 임베딩 기반).
  지금은 실행 불가 — 코드만 작성. 모듈 최상단에서 `import essentia.standard`,
  `essentia.streaming` 등 import 실패 시 `"essentia-tensorflow 미설치 — WSL2에서 실행하세요"`
  출력 후 `sys.exit(1)`.
- 모델 체크포인트: Essentia 공식 모델 저장소(essentia.upf.edu/models)의 `emomusic` 또는
  `deam` arousal 회귀 모델(`.pb`). 정확한 파일명·다운로드 URL은 WSL2 구축 시점에 확인 —
  스크립트는 `--model-path` CLI 인자로 받아 하드코딩하지 않는다(체크포인트 해시는
  `../CONVENTIONS.md` 재현성 규약대로 별도 기록).

## 산출물

`out/energy_raw.csv`:
```
idx, band, song, duration_sec,
arousal_median, arousal_p10, arousal_p90, arousal_std,
n_patches,               # 패치(MusiCNN 윈도우) 개수 — 진단용
error
```
`out/timeseries/<idx>_arousal.npy`: 패치별 원시 arousal 시계열(1D float array). 재추론 없이
재집계 가능하도록 반드시 저장.

## `extract_energy.py`

```python
def load_model(model_path: Path):
    # essentia-tensorflow의 TensorflowPredictMusiCNN(또는 해당 emomusic 전용 predictor) 로드
    # MusiCNN 임베딩 → 회귀 헤드 순전파까지 한 번에 수행하는 API를 사용(모델 파일 구조에 따라
    # 임베딩 추출과 회귀 헤드가 분리돼 있을 수 있음 — WSL2에서 essentia 문서/모델 카드로 확정)

def extract_features(path: Path, model) -> dict:
    # audio = es.MonoLoader(filename=str(path), sampleRate=16000)()  # essentia 모델 요구 SR 확인
    # arousal_series = model(audio)  # 패치별 연속값 배열
    # duration_sec, n_patches 계산
    # 요약통계(median/p10/p90/std) 계산
    # timeseries npy 저장은 호출부(worker)에서 처리
```
- 모델 로딩은 워커 1회당 1번만(멀티프로세싱 시 각 프로세스가 1번 로드) — 곡마다 재로딩 금지
  (성능). `--workers` 기본값은 모델 로딩 비용 고려해 2~4로 낮게.
- GPU 사용 가능 시 활용(essentia-tensorflow가 지원하는 범위 내). 없으면 CPU로 폴백.

## 검증 방법 (내가 수행)
- WSL2 구축 전까지 정적 리뷰만: 함수 시그니처가 SPEC과 일치하는지, resume/에러격리/CLI
  인자가 CONVENTIONS를 따르는지, timeseries 저장 로직이 있는지 확인. `python -m py_compile`로
  구문 확인.
- WSL2 구축 후 `--limit 3`으로 실제 실행해 arousal 값이 상식 범위(모델 출력 스케일 확인 필요
  — 보통 1~9 또는 0~1)에 있는지, 이미 알려진 대비곡(조용한 곡 vs 시끄러운 곡)에서 방향성이
  맞는지 확인 예정(별도 후속 작업).
