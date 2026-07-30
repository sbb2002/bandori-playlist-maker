# energy_full 검증 — energy·energy_full과 tempo·brightness·원시 오디오 피처의 관계

## 배경

`songs_master.csv`의 선곡 엔진용 `energy`(발췌구간 프록시 기반, `domain/selection.py`가
소비하는 실제 프로덕션 값)가 tempo와 상관이 있는지 확인하다가, brightness(mode_score)와도
거의 무관하다는 게 드러났다. 이어서 `energy`와 `energy_full`(전곡 재추출 보정치,
`src/scripts/data/build_energy_full.py`, 아직 프로덕션 미채택)을 비교하니 오히려 음의
상관(r≈-0.45)이 나와, `energy_full`이 실제로 무엇을 포착하는지와 그 보정이 의도대로
작동하는지를 검증했다.

## 상태: **`energy_full` 채택 보류**

핵심 검증(GT_MISJUDGED, 특히 처救生)이 절반 실패했고, ave_mujica 사례에서 조합 공식의
**장르 편향**(rms/음량 축을 배제해 "크지만 매끄러운" 강도 표현을 과소평가)까지 확인됨.
사용자 결정: 이 편향이 해소되기 전까지 `energy_full`을 실사용하는 후속 feature 작업은
머지 보류.

자세한 배경·방법·결과·결론은 **[`report/01-energy-tempo-brightness-genre-bias.md`](report/01-energy-tempo-brightness-genre-bias.md)** 참조.

## 산출물
- `src/method-1/` — 재현 스크립트 4개(energy/energy_full x brightness 히트맵, energy vs tempo 산점도).
- `fig/` — 위 스크립트가 생성한 PNG.
- `report/` — 정식 검증 보고서(위 링크).

## 참고
- `src/scripts/data/extract_full_energy.py`, `src/scripts/data/build_energy_full.py`
  (main 브랜치) — energy_full 산출 파이프라인 원본.
- 이 topic의 fig/ 이미지는 main `docs/diagrams/`에도 동일 파일명으로 복사돼 있다(로컬 검토용,
  main에는 커밋되지 않음).
