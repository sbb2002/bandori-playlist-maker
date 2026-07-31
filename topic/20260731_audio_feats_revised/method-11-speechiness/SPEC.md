# method-11-speechiness 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §11, "분포 퇴화
> 탈출 조건".

## 실행 환경
- **네이티브(Windows Python 가능)** — `extract_speechiness_stem.py`: Scheirer-Slaney 4Hz
  변조 에너지는 scipy/librosa만으로 구현 가능. **essentia/madmom 의존 없음.**
- **네이티브, 단 신규 패키지 필요** — `extract_speechiness_vad.py`: ML 교차검증은
  `pyannote.audio`(HuggingFace 토큰 필요할 수 있음) 대신 **inaSpeechSegmenter**(pip 설치,
  토큰 불필요, torch/keras 기반) 사용을 우선한다 — 설치·인증 마찰이 적은 쪽을 우선 채택.
  실패 시(패키지 미설치 등) `error="vad_unavailable"`로 기록하고 계속 진행.

## ⚠️ 스템 가용성 (CONVENTIONS.md 참조)
- 1차 방법(Scheirer-Slaney)은 **보컬 스템 필수** — 661곡 중 30곡분만 존재. 나머지는
  `error="no_stem"`으로 스킵(method-9-instrumentalness와 동일 처리 패턴 재사용).
- **풀믹스 적용 절대 금지** — CLI에 풀믹스 경로를 받는 옵션 자체를 만들지 않는다(설계상
  실수 방지).

## 산출물

`out/speechiness_raw.csv`:
```
idx, band, song, duration_sec,
speech_median, speech_p10, speech_p90, speech_std,   # 4Hz 변조 에너지 비, 보컬 스템 기준
vad_speech_ratio,           # inaSpeechSegmenter 프레임별 speech 확률의 트랙 평균(교차검증)
n_frames,
error                        # "no_stem" / "vad_unavailable" 등
```
`out/timeseries/<idx>_modulation.npy`: 프레임별 4Hz 대역 변조 에너지 비 시계열.

## `extract_speechiness_stem.py`

```python
def modulation_energy_ratio(y: np.ndarray, sr: int, frame_sec: float = 1.0) -> np.ndarray:
    # 1) envelope: y를 정류(rectify) → 저역통과(예 20Hz)로 포락선 추출
    # 2) 프레임(frame_sec 단위, 50% 겹침)마다 envelope의 스펙트럼(FFT) 계산
    # 3) 3-4Hz 대역 에너지 / 전체 변조 스펙트럼(0.5-20Hz 등) 에너지 = 해당 프레임의 비율
    # 반환: 프레임별 비율 시계열

def extract_features(band: str, idx: int) -> dict:
    paths = stem_paths(band, idx)  # method-9-instrumentalness의 헬퍼와 동일 패턴(중복 구현 무방,
                                     # 공용 모듈로 뺄 필요는 없음 — 폴더 독립성 우선)
    if paths is None:
        return {"error": "no_stem"}
    vocal_path, _ = paths
    # y, sr = librosa.load(vocal_path, sr=22050, mono=True)
    # ratio_series = modulation_energy_ratio(y, sr)
    # 요약통계 산출
```

## `extract_speechiness_vad.py`

```python
# from inaSpeechSegmenter import Segmenter
# seg = Segmenter()
# segments = seg(str(vocal_path))  # [(label, start, end), ...] label in {speech, music, noise, ...}
# vad_speech_ratio = speech로 라벨된 구간 총 길이 / 전체 길이
```
- 이 스크립트도 보컬 스템 대상으로 실행(풀믹스 아님) — DESIGN.md는 VAD 크로스체크 입력을
  명시하지 않았으나, 4Hz 방법과 같은 편향(템포 교락) 없이 일관 비교하려면 스템 기준이 합리적
  이라고 판단. 이 판단이 부적절하면 리뷰 시 재검토.

## 검증 방법 (내가 수행)
- `extract_speechiness_stem.py`는 30곡 파일럿 표본으로 즉시 실행 가능. 보컬 있는 구간 비율이
  높은 곡에서 speech_median이 상대적으로 높게 나오는지(가사 많은 파트 vs 간주 비교 등) 확인.
- VAD 스크립트는 `inaSpeechSegmenter` 설치 성공 여부에 따라 실행 검증.
