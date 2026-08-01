# method-2-key/out/key_raw.csv — 컬럼 메타데이터

> 윈도우 원시 데이터(`../timeseries/`)는 `../timeseries/metadata.md` 참고.

Krumhansl-Kessler(K-S) 템플릿 매칭(`extract_key_ks.py`, 네이티브) + Essentia
`KeyExtractor` 교차검증(`extract_key_essentia.py`, WSL2) 결과. idx 기준 병합.

| 컬럼 | 의미 |
|---|---|
| `idx` / `band` / `song` / `duration_sec` | 곡 식별자·밴드·곡명·길이(초) — `songs_master.csv` 공통 |
| `key_ks` | K-S 템플릿 매칭 다수결 최종 조성(예: `A`, `D`) — 15초 슬라이딩 윈도우별 매칭 결과를 지속시간 가중 다수결로 집계한 값 |
| `mode_ks` | K-S 다수결 최종 장/단조(`major`/`minor`) |
| `key_ks_confidence` | 다수결 1위 key/mode 조합의 누적 지속시간 ÷ 전체 지속시간(0~1). 1에 가까울수록 곡 전체가 한 조성으로 일관됨 |
| `modulation_flag` | 2위 후보의 누적 지속시간 비율이 0.25 이상이면 True — 곡 중간에 전조(modulation)가 있었을 가능성 신호 |
| `key_essentia` / `mode_essentia` | Essentia `KeyExtractor`(별도 알고리즘·크로마 기반이지만 K-S와 독립적이지는 않음)가 곡 전체에 대해 한 번에 추정한 조성/장단조 — 교차검증용 |
| `key_mismatch` | `key_ks != key_essentia`. **주의**: 근접조(관계조) 혼동을 반영하지 않은 단순 문자열 불일치이므로, 실제 판정 차이보다 부풀려져 있을 수 있음 — [[key-profile-bug-status]] 참고 |
| `mode_only_mismatch` | key는 같은데(관계조 보정 후) mode만 다른 경우 True — 청취 스팟체크 우선 대상 |
| `error` | 추출 실패 시 예외 메시지(정상 시 빈 값) |
