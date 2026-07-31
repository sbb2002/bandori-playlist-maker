# method-7-danceability 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §7.

## 실행 환경
- **WSL2 필요** — `extract_danceability_essentia.py`: Essentia `Danceability` 알고리즘(DFA
  지수, 결정론적). 지금은 실행 불가 — 코드만 작성.
- **네이티브(참고용, optional)** — `extract_danceability_dfa_native.py`: DFA는 essentia
  전용 알고리즘이 아니라 공개된 통계 기법(Detrended Fluctuation Analysis)이므로, WSL2 없이도
  RMS 에너지 시계열에 직접 DFA를 적용하는 네이티브 구현을 **참고 대조용**으로 추가 작성한다.
  단, **1차 채택은 어디까지나 Essentia 버전**(DESIGN.md 명시) — 이 네이티브 버전은 파일럿에서
  두 값의 상관을 확인하는 교차참고용이며 없어도 무방하다(시간 부족 시 생략 가능, 그 경우
  README에 "생략" 명시).

## 산출물

`out/danceability_raw.csv`:
```
idx, band, song, duration_sec,
dfa_alpha,                 # Essentia Danceability 원시 α (낮을수록 danceable)
danceability_norm,         # 0-1 정규화값(아래 규약)
dfa_alpha_native,          # 네이티브 DFA 참고값(선택, 없으면 빈칸)
danceability_clf_prob,     # ML 대체(사전학습 danceability 분류기) 확률 — Proxy, 참고용
error
```

## 0–1 정규화 규약
- 카탈로그 내 백분위 상대 정규화 채택: `danceability_norm = 1 - percentile_rank(dfa_alpha)`
  (α가 낮을수록 danceable=1에 가깝게). 이 카탈로그 661곡 분포 기준 백분위 계산.
  절대 매핑 대신 상대 정규화를 쓰는 이유는 DESIGN.md "0–1 정규화" 절 참조 — 이번 라운드는
  파일럿 소표본이라 percentile_rank는 **파일럿 표본 내부 기준**으로 계산하고, 661곡 전수
  확장 시 재계산 필요함을 코드 주석으로 남긴다.

## `extract_danceability_essentia.py`

```python
# import essentia.standard as es
# audio = es.MonoLoader(filename=str(path), sampleRate=44100)()
# danceability, dfa = es.Danceability()(audio)  # Essentia가 이미 0~... 스케일 danceability도 반환
# dfa_alpha = dfa (또는 danceability 자체 — Essentia 문서로 어느 쪽이 원시 α인지 WSL2에서 확정)
```

## `extract_danceability_dfa_native.py` (선택)

```python
# import librosa, numpy as np
# y, sr = librosa.load(path, sr=22050)
# rms = librosa.feature.rms(y=y)[0]
# DFA: 누적합(integrated series) → 구간별(window sizes) 분산의 로그-로그 회귀 기울기 = alpha
# (nolds 패키지의 dfa() 함수 사용 가능하면 그것으로 대체 — pip install nolds)
```

## 검증 방법 (내가 수행)
- Essentia 버전은 WSL2 구축 전까지 정적 리뷰만.
- 네이티브 참고 버전을 작성했다면 `--limit 5`로 즉시 실행해 값 범위 확인 가능.
