# method-6-valence 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §6.
> **이번 라운드 범위**: valence 회귀 원시 추론 + 요약통계 산출까지만. GT 캘리브레이션·대표
> 스칼라 최종 선택·`mode_score` 통계결합 보조안은 범위 밖(후속 스크립트).

## 실행 환경
- **WSL2 필요** — method-5-energy와 **동일 모델 계열**(emoMusic/DEAM, 한 번의 추론으로
  arousal·valence 동시 산출 가능). 지금은 실행 불가 — 코드만 작성.

## method-5-energy와의 관계 (중요)
- 모델이 arousal·valence를 한 번의 순전파로 동시에 뽑는 구조라면, **오디오를 두 번 읽거나
  모델을 두 번 로드하지 않는다**. `method-5-energy/src/extract_energy.py`의 `load_model`/
  오디오 로딩 로직과 중복되지 않도록, 공통 로직은 다음 중 하나로 처리:
  - (권장) 이 스크립트가 arousal·valence를 **함께** 계산해 각각
    `method-5-energy/out/energy_raw.csv`, `method-6-valence/out/valence_raw.csv`에 나눠 쓴다.
  - 또는 두 스크립트가 각자 독립 실행되도록 두되(단순성 우선), 모델이 실제로는 별도 추론
    함수라면 이 방식이 무방함.
  - **결정은 구현자(WSL2 실 실행 시점의 essentia 모델 API 확인) 재량** — 다만 어느 쪽이든
    산출 컬럼 스키마(아래)는 고정.

## 산출물

`out/valence_raw.csv`:
```
idx, band, song, duration_sec,
valence_median, valence_p10, valence_p90, valence_std,
n_patches,
error
```
`out/timeseries/<idx>_valence.npy`: 패치별 원시 valence 시계열.

## `extract_valence.py`

- 함수 구조는 `method-5-energy/src/extract_energy.py`의 `extract_features`와 대칭
  (`arousal_series` → `valence_series`로 이름만 다름). SPEC 중복을 피하기 위해 상세 API는
  method-5-energy/SPEC.md를 참조.

## 명시적 금지 사항
- `mode_score`(기존 산출물) 단독을 valence로 쓰지 않는다 — 이 스크립트에서 `mode_score`나
  `method-3-mode`의 출력을 valence 대용으로 참조/폴백하지 않는다(README.md 경고 참조).

## 검증 방법 (내가 수행)
- method-5-energy와 동일 절차(정적 리뷰 → WSL2 구축 후 `--limit 3` 실행 검증).
