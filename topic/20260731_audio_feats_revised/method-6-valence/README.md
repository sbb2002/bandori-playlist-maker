# method-6-valence

> 상세 근거는 `../DESIGN.md` §6, "GT 설계 요건", "왜 연속 회귀는 energy·valence에만 쓰나" 참조.

## 방식
- **1차**: Essentia emoMusic/DEAM 학습 **valence 연속 회귀** — method-5-energy와 **동일 모델
  계열**(arousal과 한 번의 추론으로 동시 커버). 패치 단위 시계열로 산출.
- **경(輕) Proxy** — 연속 valence 회귀라는 점에서 목적 일치, 학습 도메인 차이만 검증 필요.
- **ML 대체(격하)**: `mood_happy`/`mood_sad` 분류기 확률차 — 이진 분류기라 0/1 근처 포화되는
  경향 → 1차 후보에서 격하한 사유. **Proxy**.
- **통계적 보조**: mode(method-3) 비율 + tempo(method-1) + spectral centroid(밝기) 결합 회귀,
  GT로 가중치 학습.
  - ⚠️ **`mode_score` 단독 사용은 명시적으로 금지**(이전 결함 반복 — 장/단조 축일 뿐 이
    장르의 실제 밝기 지각과 불일치했음, `../README.md` 배경 참조).

## GT의 역할
- method-5-energy와 동일 — 캘리브레이션 검증(가중치 학습 아님, 단 통계적 보조 경로는 예외).

## 대표값 집계 (동적 피처)
- method-5-energy와 동일 규약: 요약통계 세트 산출 → GT 순위 상관 최고인 통계를 대표 스칼라로
  사전 등록 기준에 따라 채택.
