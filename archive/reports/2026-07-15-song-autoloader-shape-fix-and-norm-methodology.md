# 2026-07-15 — song-autoloader shape/energy 버그 수정 + 동결 norm 방법론 검토

## 배경

`feature/song-autoloader` 브랜치는 다른 로컬(경로 구조 `pyworks/...`, 형제 레포 wav 캐시 보유)에서
작업 중 세션 토큰이 소진되며 `wip(autoloader): 세션 마감 스냅샷`(`c2f3f59`) 상태로 커밋·푸시됐다.
이 문서는 별도 로컬(`bandori-playlist-maker`, 원본 오디오 데이터 없음)에서 이어받아 진행한 내용을
기록한다.

## 1. KeyError 버그 수정 (커밋 `fb7a53e`)

`merge_data.assemble_master_row`가 `audio_entry["energy"]`/`["shape"]`를 직접 인덱싱했는데,
형제(`bandori-song-sorter`) `audio_map.json`의 신곡 엔트리에는 이 두 키가 더 이상 없어(형식 변화)
dry run이 KeyError로 죽는 문제였다.

- `energy`: song_repo가 소비하지 않는 레거시 컬럼 → `audio_entry.get("energy", "")`로 공란 허용.
- `shape`: song_repo가 **소비함**(`Song.shape`). 형제 `add_pulse_shape.py`
  (`bandori-song-sorter/src/tools/cluster/add_pulse_shape.py`)의 채널 산식을 확인해 이식:
  `acoustic=z(harmonic_ratio)`, `bright=mean(z(centroid,rolloff,zcr,flatness))`,
  `shimmer=z(flux)`, 최댓값 채택·gap<0.4면 neutral (z-score ddof=0). 형제 audio_map에 더 이상
  의존하지 않고 우리 발췌 특징(`excerpt_features.extract_from_wav`가 6개 원시값을 이미 반환)에서
  직접 계산하도록 `norms.py`에 4번째 동결 norm(`data/shape_norm.json`)으로 추가했다.

`test_merge_data.py`/`test_norms.py`에 합성 데이터 기반 테스트를 추가(실오디오 불필요).
전체 `python -m pytest` 231 passed, autoloader 단위테스트 35 passed.

## 2. 이 로컬에서의 검증 범위와 한계

이 로컬은 원본 wav가 없지만 660곡 분석 산출물(`data/` 6종 CSV/JSON)은 전부 갖고 있어, 다음까지는
실측 검증이 가능했다:

- **신곡 감별**: `sources.py`가 `git show origin/main:...`으로 형제 레포의 로컬 체크아웃 브랜치와
  무관하게 원격 `main`을 직접 읽으므로, 이 로컬에서도 정상 동작 확인. 형제 origin/main 663행 vs
  master 658행 → 신곡 3곡(idx 660~662, 전부 mygo) 정확히 감별됨 — 사용자가 전날 확인한 신곡 3곡과
  일치.
- **shape 동결 norm 재현**: 로컬 660곡 실데이터로 `build_shape_norms`/`compute_shape`를 돌려
  기존 저장값과 대조한 결과 **exact 659/660**. 유일한 불일치는 idx 570(`roselia`/`Neo-Aspect`) —
  이는 형제 `add_pulse_shape.py` 자체가 docstring에서 경고한 동명곡 조인 한계다. idx 570은
  idx 588(같은 `roselia`/`Neo-Aspect`, [[2026-07-13-boundary-tension-sensitivity-open-question]]
  문서에 기록된 **확인된 중복 업로드**, PR #7에서 master에서 제거됨)과 `(band,song)` 키가 완전히
  같아 형제 스크립트의 `(band,song)→idx` 매핑이 둘 중 하나로 붕괴한다 — 우리 포팅 문제가 아니라
  원본 데이터의 기존 결함을 물려받은 것. 99% 문턱은 통과하므로 자동 구축엔 지장 없음.
- **intensity_norm 부트스트랩**: **실패**. 형제 레포 dev 캐시에 wav가 285/660(43%)만 있어 전역
  med/MAD가 크게 어긋남(실측: exact 0/1710, max diff 0.77 — 허용치 5e-4의 약 1500배). 이 값은
  원본 파형을 다시 읽어야만 나오는 값이라 CSV 산출물만으로는 대체 불가 — 원본 wav가 있는 로컬에서
  마저 진행해야 하는 유일한 단계로 확인.

## 3. median/MAD 정규성 가정 검토

`energy_full`/`intensity_norm`이 쓰는 강건정규화(median/MAD, `σ_robust = 1.4826 × MAD`의 1.4826은
정규분포 가정 하 스케일링 상수)가 실제로 정당화되는지 이 로컬 데이터(`full_audio_features.csv`,
660곡)로 Shapiro-Wilk 검정을 실측했다.

| col | skew | kurtosis | Shapiro-W | p-value |
|---|---|---|---|---|
| perc_mean | -0.297 | 0.230 | 0.9896 | 1.29e-04 |
| onset_mean | 2.100 | 8.966 | 0.8626 | 1.40e-23 |
| zcr_mean | -0.019 | 0.149 | 0.9971 | 2.92e-01 |
| cen_mean | -0.253 | 0.557 | 0.9947 | 2.11e-02 |
| flat_mean | 0.746 | 1.823 | 0.9716 | 5.19e-10 |
| rms_p90 | -0.256 | 3.952 | 0.9502 | 3.95e-14 |

**결론: 정규성 가정은 대부분 컬럼(특히 onset_mean)에서 실측으로 기각된다.** 다만 실질적 피해는
없는 것으로 판단된다 — `energy_full`(`EnergyFullFrozen._pct`)과 `i_min/i_mean/i_end`
(`song_repo._percentile_ranker`) 모두 최종적으로 **전 곡 대비 백분위 순위**로만 소비되고, 백분위
순위는 모든 곡·모든 피처에 동일하게 곱해지는 양의 상수(1.4826)의 정확한 값에 불변이다. 즉 1.4826이
틀렸어도 곡 간 상대 순서(선곡 엔진이 실제로 쓰는 값)는 바뀌지 않는다. `shape`는 이 이슈 대상이
아니다(MAD가 아니라 mean/std(ddof=0)만 사용, 임계값 0.4와 직접 비교).

## 4. 결정 (사용자 확정, 2026-07-15)

- 동결 norm 방식은 현행 유지한다. 코드 변경 없음.
- 향후 필요시 "N곡(예: 10~50곡) 추가마다 주기적으로 norm 재구축" 정책을 도입할 수 있음 —
  `load_or_build_*` 함수들이 이미 "json 없으면 재구축" 구조라, `json_path`를 주기적으로 삭제하는
  정도로 확장 가능(현재는 미구현, 필요 시점에 결정).
- **주의**: `research/mood-warmth-feature` 브랜치에서 새 변수(피처)를 연구 중이며, 그 결과가
  채택되면 오토로더의 컬럼 선택·산식(`norms.py`)도 재검토 대상이 될 수 있음. 이번 수정에는
  반영하지 않음(사용자 확정).

## 관련

- 코드: `feature/song-autoloader` 브랜치 커밋 `fb7a53e`
- `RESUME-song-autoloader.md`(해당 브랜치) — 다음 재개 순서(원본 wav 로컬에서 dry run 마무리)
- [[2026-07-13-boundary-tension-sensitivity-open-question]] — idx 570/588 중복 업로드 배경
