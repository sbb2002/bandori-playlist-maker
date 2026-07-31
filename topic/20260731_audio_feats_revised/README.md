# audio_feats_revised: 음원 피처 전면 재산출 (topic/20260731_audio_feats_revised)

## 배경

`energy`/`energy_full`(선곡 엔진의 강도 신호)와 `mode_score`(밝기/valence 대리)에 대해 그동안
누적된 검증 결과가 전부 부정적으로 나왔다 — `energy_full`은 GT_MISJUDGED 절반 실패에 핵심
가중치(`rms_p90`)가 곡 1개(FIRE BIRD)에 소표본 과적합된 상태이고, `mode_score`는 장/단조
축일 뿐 이 장르의 실제 밝기(valence)와 불일치한다(가장 밝게 들리는 곡이 오히려 하위권).
`decision-energy-full-blocked-genre-bias` 메모에 따라 energy·valence 산출 파이프라인 전체를
"날 잡아서" 재설계하기로 이미 결정돼 있었고, 이 폴더가 그 착수다.

기존 프록시들(`energy_proxy`/`acousticness_proxy`/`instrumentalness_proxy`/`mode_score`,
`bandori-song-sorter/side-project/genre-features/`)의 산출 방식을 되짚어본 결과, 사용자
판단으로 **연구 설계 단계 자체에 치명적 결함**이 있었다:
- 전 곡 **중앙 45초 발췌**만으로 피처를 추출해 곡 전체를 대표하지 못함(가장 큰 문제로 지목).
- 검증 대상이 실제 타깃(무드 지각)이 아니라 **밴드(장르) 판별력**이었음 — 밴드는 잘 갈라도
  무드 매칭이 맞는지는 애초에 검증한 적이 없음.
- 가중치가 학습된 게 아니라 **임의 균등(1:1) z-점수 합**이었음(비선형·상호작용도 미반영).

**그래서 이 연구는 기존 코드·공식·산출값을 재참조하지 않고 완전히 처음부터 다시 설계한다.**
`energy_proxy`/`acousticness_proxy`/`mode_score`/`energy_full` 등 기존 산출물은 참고 대상이
아니라 "이렇게 하면 안 된다"는 반면교사로만 취급한다.

## 목적

`energy`(강도)·`valence`(밝기)를 곡 전체 오디오에서, 실제 지각 타깃(사람이 느끼는 강도·밝기)에
대해 검증 가능한 방식으로 재산출한다. 구체적 방법론(신호처리 조합 vs 학습 모델 vs 다른 접근)은
아직 미정 — 이 폴더 안에서 설계부터 새로 시작한다.

## 참고(반면교사 — 재사용 금지)

- `decision-energy-full-blocked-genre-bias`(메모리) — 기존 파이프라인 결함 결정 근거.
- `topic/20260730_energy_full_validation/` — `energy_full`의 구체적 실패 사례(GT_MISJUDGED,
  rms_p90 과적합).
- `bandori-song-sorter/side-project/genre-features/README.md` — 기존 프록시 산출 방법과 그
  한계(45초 발췌, 밴드 판별력 검증, 임의 가중치)가 기록된 원본.

## 다음 단계

방법론 설계(전곡 오디오 접근 방식, ground truth 확보 방법, 검증 절차)부터 시작. 아직 착수 전.
