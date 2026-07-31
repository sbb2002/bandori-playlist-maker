# method-3-mode

> 상세 근거는 `../DESIGN.md` §3 참조.

## 방식
- 별도 산출 아님 — **method-2-key** 산출 시 매칭된 템플릿(k, m)의 m(장조/단조)을 그대로 사용.
- 신뢰도는 key 교차검증(K-S vs Essentia `KeyExtractor`)의 "모드만 불일치" 비율로 평가
  (K-S의 고전적 오류 패턴이 관계장/단조 혼동이기 때문).
- 통계적 방법, proxy 아님.

## 주의
- `mode_score`(기존 산출물) 단독 사용은 valence 대리로 부적합함이 이미 확인됨(반면교사,
  `../README.md` 참조) — 장/단조 축이지 valence 자체가 아님. 이 원칙은 method-6-valence에도
  명시적으로 반영됨.
