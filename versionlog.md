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

### v1.0.2 — 2026-07-20 12:05 (Patch)

오토로더 신곡 1곡 반영(커밋 `4945309`, 서브 로컬 `--soft` 실행 — 단, `intensity_norm.json`
동결 상수가 이미 있어 폴백 미발동, `i_*` 포함 전 지표 실측 산출·provisional 없음).

- 추가 곡: `ikka_dumb_rock` · Keep on Riddim · https://youtu.be/h0QJo5XjosA
- 현재 총 곡 수: **663곡** (`data/songs_master.csv`)
- 부수: `shape_norm.json` 워크트리 잔존 사본(07-16 재빌드, 663곡 기준 — 동결 원칙 위반)을
  폐기하고 커밋본(07-15, 원시 660곡 기준)으로 정리.

### v1.0.1 — 2026-07-19 01:48 (Patch, 소급 기록)

오토로더 신곡 1곡 반영(커밋 `9b4ebb9`). 반영 당시 이 로그가 갱신되지 않아 소급 기록한다.

- 추가 곡: `millsage` · カーネーションの咲く日に · https://youtu.be/-CFoE43oPOk
- 현재 총 곡 수: **662곡**

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
