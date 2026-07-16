# data 브랜치 Version Log

`main`의 앱 버전(`v1.x.x`, 배포 릴리스 단위)과는 **별개의 독립 버전 체계**다. 이 브랜치는
`data/` 데이터셋 자체의 변경만 기록한다.

## 버전 규칙

| 단위 | 트리거 |
|---|---|
| **Major** | 데이터 구조 또는 컬럼의 전면 개편 (예: 스키마 재설계, 조인 키 변경) |
| **Minor** | 컬럼 추가·제거·편집 (예: 새 파생 지표 컬럼 추가) |
| **Patch** | 신곡 추가 |

## 작성 규칙

매 항목에 다음을 남긴다:
- **버전**(`vX.Y.Z`)
- **날짜시각**(`YYYY-MM-DD HH:MM`, KST)
- **작업내역**: 무엇이 바뀌었는지 + **현재 총 곡 수**(`data/songs_master.csv` 기준, 상시 표시)
- **Patch(신곡 추가)인 경우**: 추가된 각 곡의 `band`·`song`·`url`을 전부 나열한다.

## Log

### v1.0.0 — 2026-07-16 (baseline)

브랜치 재편(`data/` 외 전 파일 제거, `main` 스냅샷 잔재 정리) 시점의 데이터셋 스냅샷을
이 독립 버전 체계의 기준점으로 삼는다. 이전 이력(658곡 마스터 구축 → 3곡 자동 추가)은
git 커밋 로그(`git log -- data/songs_master.csv`)로 추적 가능하나, 이 버전 로그 자체는
여기서부터 시작한다.

- 현재 총 곡 수: **661곡** (`data/songs_master.csv`)
- 파일 구성: `songs_master.csv`(canonical) · `songs_full.csv` · `song_features_with_proxies.csv` ·
  `full_audio_features.csv` · `temporal_intensity.csv` · `audio_map.json` ·
  `feature_norms.json` · `energy_full_norm.json` · `intensity_norm.json` ·
  `legacy/`(구버전 스냅샷 2종)
