# method-9-instrumentalness

> 상세 근거는 `../DESIGN.md` §9, "분포 퇴화 탈출 조건" 참조.

## 방식
- **1차**: Essentia 사전학습 `voice_instrumental` 분류기(voice/instrumental 확률).
  **경 Proxy** — 개념 일치, 출처 모델 다름.
- **통계적 교차검증**: 보유 스템 활용(신규 소스분리 실행 불필요, 비용 0 — **단 아래 참고 확인**)
  `instrumentalness = 1 − (vocal_stem_energy / total_energy)`. 분류기와 순위 상관으로 상호 검증.
  **Proxy**(분리 결과의 재해석).

## ⚠️ 스템 가용성 확인 필요
- DESIGN.md는 "메인 로컬에 보컬/악기 분리 스템 보유(신규 소스분리 불필요)"를 전제했으나,
  실측 결과 `bandori-playlist-maker/topic/mfcc_analysis/stems/htdemucs/`에는 **661곡 중
  30곡분만** htdemucs 4-source(vocals/drums/bass/other) 분리본이 존재.
  `bandori-song-sorter/.../audio_drums/`(712곡)는 드럼 전용 분리로 보컬 스템이 아님.
- 661곡 전수 확장 전 나머지 곡의 htdemucs 4-source 분리를 새로 돌려야 함 — 파일럿(30곡)은
  기존 스템으로 가능하나, 정식 확장 단계에 이 작업을 별도 반영 필요.

## ⚠️ 분포 퇴화 위험
- method-8-acousticness와 동일 사유로 저값 대역 쏠림 가능 → 파일럿에서 분산·변별력 점검 필수.

## 대표값 집계 (정적 피처)
- 기본 대표값 = 중앙값. std는 진단 지표.
