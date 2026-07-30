# energy_full 검증 — energy·energy_full과 tempo·brightness·원시 오디오 피처의 관계

## 배경

`songs_master.csv`의 선곡 엔진용 `energy`(발췌구간 프록시 기반, `domain/selection.py`가
소비하는 실제 프로덕션 값)가 tempo와 상관이 있는지 확인하다가, brightness(mode_score)와도
거의 무관하다는 게 드러났다. 이어서 `energy`와 `energy_full`(전곡 재추출 보정치,
`src/scripts/data/build_energy_full.py`, 아직 프로덕션 미채택)를 비교하니 오히려 **음의
상관**(r≈-0.45)이 나와, `energy_full`이 실제로 무엇을 포착하는지와 그 보정이 의도대로
작동하는지를 함께 확인했다.

## 방법

`src/method-1/`(4개 스크립트) 참조 — energy/energy_full x brightness 2D 히스토그램,
energy vs tempo 산점도. brightness는 `domain/selection.py`의 `_brightness_scores()`를
그대로 재현.

추가로(대화 중 1회성 확인, 별도 스크립트 파일 없음):
- `data/full_audio_features.csv`(zcr·spectral centroid/rolloff/flatness/contrast·HPSS
  percussive·onset·rms 등 전곡 원시 서브피처)와 `energy_full`의 Pearson r.
- `build_energy_full.py`에 정의된 ground-truth 라벨(GT_QUIET 14곡·GT_LOUD 14곡·
  GT_MISJUDGED 8곡, STRICT4)로 `songs_master.csv`에 실제 반영된 `energy_full` 순위를
  재검증(순위 계산만, eligible+energy_full 있는 730곡 기준).

## 결과

**1. `energy`(프로덕션)는 tempo·brightness와 거의 무관.**
tempo_excerpt r=-0.06, bpm r=-0.05, mode_score r=-0.06. `i_min`(전곡 프레임강도 최솟값,
r=+0.35)·`i_std`(변동폭, r=-0.37) 쪽이 더 관련 있음 — "가장 조용한 순간이 없다(=다이나믹
레인지가 좁다)"에 가까움. → `fig/heatmap_overall.png`, `fig/heatmap_by_band.png`,
`fig/energy_vs_tempo.png`.

**2. `energy_full`은 원시 스펙트럼/타악 피처와 강하게, 그리고 해석 가능하게 상관된다.**
zcr(r=+0.76)·spectral flatness(+0.71)·spectral centroid(+0.68)·HPSS percussive
energy(+0.60)·onset strength(+0.47) 모두 강한 양의 상관, spectral contrast는 음의 상관
(-0.27, 왜곡음일수록 잡음바닥이 올라가 대비가 줄어드는 것과 부합). acousticness_proxy와는
r=-0.65로 강한 음의 상관. 즉 `energy_full`이 높을수록 "거칠고 노이즈성 강한, 타악기
비중이 큰, 어쿠스틱하지 않은" 사운드 — 방향성 자체는 잘 잡혀 있다. `mode_score`(r=-0.10)·
tempo(r=+0.08)와는 `energy`와 마찬가지로 거의 무관. → `fig/heatmap_energyfull_brightness.png`,
`fig/heatmap_energyfull_brightness_byband.png`.

**3. 그런데 `build_energy_full.py`가 명시한 핵심 검증(GT_MISJUDGED)은 절반이 실패했다.**
STRICT4(★조용한 인트로에 속아 오판된 실제 시끄러운 곡, 반드시 상위로 끌어올려야 함) 4곡 중
2곡(ドラマチック！アライブ rank 616/730, はいよろこんで rank 628/730)은 성공했지만, 나머지
2곡은 실패 — 특히 **処救生(idx=278, mygo)은 전체 730곡 중 energy_full 최하위(rank 1)**로,
스크립트가 이 컬럼을 만든 이유 그 자체인 곡에서 정반대 결과가 나왔다. GT_QUIET(14곡)·
GT_LOUD(14곡) 그룹은 대체로 방향대로 맞음(예외 1~2곡 정도).

## 결론

`energy_full`은 (a) 집계 상관 수준에서는 "시끄러움/거칠음"을 원시 오디오 피처 기준으로
`energy`보다 훨씬 잘 설명하지만, (b) 정작 이 컬럼을 만든 핵심 동기(조용한 인트로+폭발적
후렴 구조의 오판 교정)에 대해서는 검증이 완전히 끝나지 않은 상태다 — 최소 처救生 사례는
명백한 미해결. 아직 `main` 프로덕션 `energy`를 대체하지 않았으므로 당장 영향은 없지만,
이 컬럼을 향후 채택하려면 GT_MISJUDGED 그룹, 특히 STRICT4 전원이 통과하도록 조합 공식(현재
`build_energy_full.py`의 후보 서브피처 가중/부호 결정 로직)을 다시 봐야 한다.

## 참고
- `src/scripts/data/extract_full_energy.py`, `src/scripts/data/build_energy_full.py`
  (main 브랜치) — energy_full 산출 파이프라인 원본.
- 이 topic의 fig/ 이미지는 main `docs/diagrams/`에도 동일 파일명으로 복사돼 있다(로컬 검토용,
  main에는 커밋되지 않음).
