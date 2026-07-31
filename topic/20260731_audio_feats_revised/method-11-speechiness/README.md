# method-11-speechiness

> 상세 근거는 `../DESIGN.md` §11, "분포 퇴화 탈출 조건" 참조.

## 방식
- **1차**: Scheirer-Slaney(1997) 4Hz 변조 에너지를 **보컬 스템**(보유)에 적용.
  `modulation_energy = bandpass(envelope_spectrum, 3–4Hz)` 에너지 비.
  통계적, proxy 아님(단 스템 분리 품질에 의존).
  - ⚠️ **풀믹스 적용 절대 금지** — 4분음표 주기가 180BPM=3Hz, 240BPM=4Hz라 드럼 리듬이 탐지
    대역과 정면 교락(이 카탈로그는 고속곡 다수라 풀믹스에선 사실상 템포를 측정하게 됨).
- **ML 교차검증**: inaSpeechSegmenter 또는 pyannote VAD — 프레임별 speech 확률의 트랙 평균.
  **Proxy** — 이진 speech/non-speech만 주고 랩·팟캐스트류 세분화(원 정의)는 없음.

## ⚠️ 스템 가용성 확인 필요
- method-9-instrumentalness와 동일 이슈 — 보컬 스템이 661곡 중 30곡분만 존재
  (`bandori-playlist-maker/topic/mfcc_analysis/stems/htdemucs/`). 정식 확장 전 나머지 곡
  htdemucs 4-source 분리 필요.

## ⚠️ 분포 퇴화 위험
- 밴드 사운드·보컬곡 위주 카탈로그 → 저값 대역 쏠림 가능. 파일럿에서 분산·변별력 점검 필수.

## 대표값 집계 (정적 피처)
- 기본 대표값 = 중앙값. std는 진단 지표.
