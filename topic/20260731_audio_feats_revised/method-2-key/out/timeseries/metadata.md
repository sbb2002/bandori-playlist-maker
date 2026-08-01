# method-2-key/out/timeseries — 컬럼 메타데이터

`<idx>_key_windows.csv` — 곡 1개당 파일 1개(`0_key_windows.csv` ~ `660_key_windows.csv`,
661개). `../key_raw.csv`의 `key_ks`/`mode_ks`/`key_ks_confidence`/`modulation_flag`는
이 원시 윈도우 데이터를 지속시간 가중 다수결로 집계한 결과물이다 — 재집계나 다른 윈도우
크기 실험 시 이 파일을 그대로 재사용하면 오디오를 다시 열 필요 없다.

| 컬럼 | 의미 |
|---|---|
| `window_start_sec` / `window_end_sec` | 슬라이딩 윈도우 구간(초). 윈도우 길이 기본 15초, 50% 겹치게(stride = window/2) 슬라이딩 — 마지막 윈도우는 곡 길이에 맞춰 잘림 |
| `key` | 해당 윈도우의 평균 크로마 벡터(`librosa.feature.chroma_cqt`)와 24개 K-S 템플릿(장조 12 + 단조 12, 각각 12키 회전) 중 피어슨 상관이 가장 높은 조성 |
| `mode` | 위 최고 상관 템플릿의 장/단조 |
| `corr` | 그 최고 상관계수(피어슨, -1~1) — 값이 낮으면(대략 0.7 미만) 해당 구간의 조성 판정 신뢰도가 낮다는 뜻(무조성 간주/타악기 위주 구간 등) |

**집계 로직** (`extract_key_ks.py`): `(key, mode)` 조합별로
`window_end_sec - window_start_sec`(지속시간)을 합산해 최댓값을 가진 조합을 `key_raw.csv`의
`key_ks`/`mode_ks`로 채택. `key_ks_confidence` = 1위 조합 누적시간 / 전체 윈도우 지속시간
합, `modulation_flag`는 2위 조합의 그 비율이 0.25 이상인지 여부(곡 중간 전조 가능성 신호).
