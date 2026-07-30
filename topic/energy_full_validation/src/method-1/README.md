# method-1 — energy/energy_full x brightness·tempo 2D 히스토그램 + GT 재검증

## 무엇인가

`songs_master.csv`의 기존 `energy`(발췌구간 프록시 기반)와 `energy_full`(전곡 재추출
보정치, `src/scripts/data/build_energy_full.py`가 산출)이 서로 얼마나 다른지, 그리고
각각이 tempo·brightness(mode_score+shape)와 실제로 관계가 있는지를 상관계수·2D
히스토그램으로 확인한다. brightness 계산식은 `domain/selection.py`의
`_brightness_scores()`(mode_score min-max 정규화 + shape 보조가중, eligible_band 풀
전체 1회 정규화)를 그대로 재현한다.

## 어떻게 실행했는지

1. `plot_heatmaps.py` — `energy` x `brightness` 2D 히트맵(전체 + 밴드별 소형멀티플).
2. `plot_energy_tempo.py` — `energy` vs `tempo_excerpt` 산점도 + Pearson r.
3. `plot_energyfull_brightness.py` — `energy_full` x `brightness` 2D 히트맵(전체).
4. `plot_energyfull_brightness_byband.py` — 위와 동일하되 밴드별 소형멀티플.

4개 스크립트 모두 `data/songs_master.csv`(이 브랜치의 데이터 스냅샷)를 직접 읽고,
결과 PNG를 `../../fig/`에 저장한다. 실행:

```
python plot_heatmaps.py
python plot_energy_tempo.py
python plot_energyfull_brightness.py
python plot_energyfull_brightness_byband.py
```

`data/full_audio_features.csv`(전곡 원시 서브피처: zcr·spectral centroid/rolloff/
flatness/contrast·HPSS percussive·onset·rms)와 `energy_full`의 상관, 그리고
`src/scripts/data/build_energy_full.py`에 정의된 ground-truth 라벨(GT_QUIET/GT_LOUD/
GT_MISJUDGED)로 실제 순위를 재검증하는 부분은 대화 중 1회성 스크립트로 수행했고
(별도 파일로 남기지 않음), 핵심 결과는 이 폴더의 상위 `README.md`에 요약돼 있다.
