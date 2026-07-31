# method-7-danceability

> 상세 근거는 `../DESIGN.md` §7 참조.

## 방식
- **1차**: Essentia `Danceability` — 에너지 시계열의 **DFA(Detrended Fluctuation Analysis)
  지수 α**(낮을수록 리듬 규칙적=danceable). 결정론적, ML 아님, proxy 아님.
  - 원시 α는 0–1이 아니므로 "0–1 정규화" 공통 규약 적용 필요(카탈로그 내 백분위 상대
    정규화 vs 절대 매핑 중 결정).
- **ML 대체**: Essentia 사전학습 `danceability` 분류기(MusiCNN 임베딩 + transfer learning).
  Spotify 정의를 직접 학습한 모델이 아니라 별도 라벨셋 기반 — **Proxy**.

## 대표값 집계 (정적 피처)
- 기본 대표값 = 중앙값. std는 진단 지표(예: 곡 내 리듬 규칙성 변동 감지).
