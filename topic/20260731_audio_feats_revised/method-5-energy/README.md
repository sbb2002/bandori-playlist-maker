# method-5-energy

> 상세 근거는 `../DESIGN.md` §5, "GT 설계 요건", "왜 연속 회귀는 energy·valence에만 쓰나" 참조.

## 방식
- **1차**: Essentia emoMusic/DEAM 학습 **arousal 연속 회귀**(MusiCNN 임베딩,
  essentia-tensorflow). 패치 단위 시계열로 산출.
- **경(輕) Proxy** — arousal은 energy와 개념적으로 근접하나 동일 정의는 아니고, 학습 데이터가
  서구권 일반 음악이라 이 장르 일반화는 GT 검증 필수.
- **대체(회귀가 GT 검증에서 실패할 때만)**: loudness(method-4) + spectral contrast z +
  onset rate z + 다이나믹레인지(EBU R128 LRA 우선, 또는 RMS p95−p5) z 결합.
  가중치는 반드시 **자체 GT로 회귀 학습**(임의 균등합 금지).

## GT의 역할
- 가중치 학습이 아니라 **캘리브레이션 검증**(모델 출력과 GT 간 단조성·순위 상관 확인).
- 통계 결합 대체안으로 갈 때만 가중치 "학습"이 필요.

## 대표값 집계 (동적 피처)
- 요약통계 세트(중앙값·p10·p90·표준편차) 전부 산출 후, **어느 통계가 GT와 순위 상관이
  가장 높은지**로 대표 스칼라 채택 — 판정 기준 사전 등록 필수(임의로 상위분위 고르기 금지,
  `energy_full`의 rms_p90 과적합 재발 방지).

## 과적합 방지
- train/holdout 분리를 먼저 하고 holdout은 최종 1회만 사용.
- 통계 결합 대체안 회귀 시 LOOCV + 정칙화, 피처 수 상한(라벨 수의 1/10 이하).
