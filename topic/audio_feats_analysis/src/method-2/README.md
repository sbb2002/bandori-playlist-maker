# Method 2: 템포(BPM) 확정 — 옥타브 후보 선출 + bestdori 공식값 검증·통합

`audio_feats_analysis` 연구는 곡의 음향 피쳐를 축별로 확정해 나가는 topic이며(템포 외에
키/조성 등 추가 분석 예정), **method-2는 그중 템포 축**을 담당한다. `report/01`(옥타브
모호성 조사) §6.2의 후속 작업으로, 드럼 스템 기반 `drum_tempo_bpm`의 옥타브(2배/절반)
오류를 해소해 곡당 신뢰 가능한 BPM 1개를 확정하는 것이 목표다.

오디오 없이 기존 CSV의 ACF 컬럼과 bestdori API만 사용하므로 **어느 로컬에서든 실행
가능**하다. 결과 해석·수치는 `report/02-bestdori-bpm-validation.md` 참조.

## 방법론 요약

1. **후보 생성**: `drum_tempo_bpm × 2ⁿ`(n=−1..1) 중 장르 관측 범위 [85,220]에 드는
   값만 후보로 남긴다(±2옥타브는 전곡에서 범위 밖).
2. **검증**: 후보 중 1개를 고르는 규칙(τ=0.96 ACF 규칙 vs 최대 후보 규칙)을 bestdori
   공식 BPM(게임 채보 기반, 옥타브 오류 없음) 573곡과 ±4%(MIREX 관행) 기준으로 대조.
3. **결론 반영**: ACF는 옥타브 방향 판별력이 없어 폐기, "범위 내 최대 후보" 규칙 채택.
   최종본은 공식 BPM 우선(573곡) + 미매칭 88곡만 추정치로 통합.

## 스크립트 역할과 실행 순서

```bash
cd topic/audio_feats_analysis/src/method-2
python 01_select_bpm.py       # 후보 생성 + τ 규칙 선출(661곡) -> out/bpm_selected.csv
python 02_fetch_bestdori.py   # bestdori 매칭·공식 BPM 수집     -> out/bestdori_bpm.csv
python 03_compare.py          # 규칙별 오차·정확도 산출          -> out/bpm_validation.csv
python 04_build_final_bpm.py  # 최종 BPM 통합본(공식 우선)       -> out/bpm_final.csv
```

- `config.py` — 경로·상수(범위 [85,220], τ, 밴드 ID 매핑, ±4% 허용오차) 단일 출처.
- `01_select_bpm.py` — 곡별 후보 개수와 τ 규칙 선출 결과를 기록한다. τ 규칙은 검증
  결과 폐기됐지만, 어떤 곡이 왜 모호했는지(rule/decision_ratio)의 진단 기록으로 남긴다.
- `02_fetch_bestdori.py` — bandId+정규화 제목(NFKC·casefold·공백 제거·〜/～ 통일)으로
  매칭하되 `(Cover)` 접미사 제거 → 말미 괄호구 제거 → 전역 유일 제목 순으로 완화.
  API 응답은 `out/bestdori_cache/`(gitignore)에 캐시되어 재실행 시 재다운로드가 없다.
  BPM 변화곡은 구간 길이 가중 지배값을 취한다.
- `03_compare.py` — Accuracy1(옥타브 불허)/Accuracy2(옥타브 허용)와 오차 mean/std를
  τ 규칙·최대 후보 규칙 각각에 대해 산출한다.
- `04_build_final_bpm.py` — report/02 §3 결론의 구현체. 다른 분석이 템포 값을 쓸 때는
  이 산출물(`bpm_final.csv`)을 참조하면 된다.

Windows 콘솔에서는 `python -X utf8`로 실행(cp949 인코딩 에러 방지).

## 산출물 컬럼 사전

### out/bpm_final.csv (661곡 — 최종본, 타 분석은 이것만 보면 됨)
| 컬럼 | 의미 |
|---|---|
| `idx`/`tag`/`band`/`song` | 카탈로그 식별자(audio_feats.csv와 동일 키) |
| `drum_tempo_bpm` | 드럼 스템 기반 원 추정값(형제 프로젝트 산출, 옥타브 미보정) |
| `bestdori_id` | 매칭된 bestdori 곡 ID(미매칭이면 공란) |
| `official_bpm` | bestdori 공식 BPM(변화곡은 구간 길이 가중 지배값) |
| `n_unique_bpm` | 곡 내 BPM 변화 개수(1이면 단일 BPM 곡) |
| `estimated_bpm` | "[85,220] 내 최대 후보" 규칙 추정치 |
| `final_bpm` | **최종 확정 BPM** = official 있으면 official, 없으면 estimated |
| `bpm_source` | `official`(573곡) / `estimated`(88곡) |

### out/bpm_selected.csv (661곡 — τ 규칙 선출 + 진단 기록)
| 컬럼 | 의미 |
|---|---|
| `n_candidates` | [85,220] 내 옥타브 후보 개수(1 또는 2) |
| `rule` | 적용 규칙: `unique`(후보 1개)/`acf_up`({base,×2})/`acf_down`({÷2,base}) |
| `decision_ratio` | 판정에 쓰인 ACF 비율(pulse_ratio 또는 pulse_ratio_down) |
| `octave_shift` | τ 규칙이 고른 옥타브(−1/0/+1) |
| `selected_bpm` | τ 규칙 선출값(검증 결과 신뢰 불가 — final_bpm을 쓸 것) |
| `base_in_range` | False면 base 자체가 범위 밖이라 ACF 근거 없이 접힌 곡(74곡) |

### out/bpm_validation.csv (573곡 — 공식값 대조 상세)
| 컬럼 | 의미 |
|---|---|
| `err_strict_pct` | τ 규칙 선출값의 공식 BPM 대비 signed 오차(%) |
| `official_folded`/`fold_shift` | 공식 BPM×2ⁿ 중 선출값에 로그 최근접인 값과 그 n |
| `err_octave_pct` | 옥타브 접은 오차(%) — 주파수 정밀도 지표 |
| `octave_error` | fold_shift≠0, 즉 옥타브 자체를 틀린 곡 |
| `selected_bpm_maxrule`/`err_maxrule_pct` | 최대 후보 규칙 선출값과 그 오차(%) |
| `match_method` | bestdori 매칭 경로(`band+title`/`title-unique`) |
| `dominant_coverage` | 지배 BPM이 곡 길이에서 차지하는 비율 |

## 핵심 결론 (2026-07-20)

- 옥타브 접은 오차 mean +1.1% / std 5.8% — ACF 주파수 정밀도는 우수.
- τ=0.96 ACF 규칙은 옥타브 판별력 없음(Accuracy1 53.4%) → **폐기**.
- "[85,220] 내 최대 후보" 규칙이 Accuracy1 92.5%로 실용 최적.
- 최종본 `bpm_final.csv`: official 573 + estimated 88, 실측 범위 [75,260].
