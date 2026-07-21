# `KS_PROFILES` 버그 수정 반영 — 661곡 재산출 및 tunebat 재검증 (report/06 §7 후속)

**세션일**: 2026-07-21. `report/06`이 메인 기기로 인계한 §7 작업(661곡 전체 재산출·재검증)을
이 세션(메인 로컬 환경)에서 실행했다. 원본 오디오(664개 wav)가 이 기기에 있어 처리 가능했다.

## 1. 재산출

`config.py`의 `KS_PROFILES` 부호 수정(report/06 §3·§6, 이미 완료된 상태)을 반영해
`extract_features.py`를 661곡 전체 재실행했다. 기존 `progress.json`이 버그 수정 전 결과를
캐시하고 있어(`process_song`이 캐시 hit 시 재계산을 건너뜀), 재실행 전 `progress.json`과
`audio_feats.csv`를 `*.bak_prebugfix`로 백업 후 `progress.json`을 삭제해 전체 재계산을
강제했다. 661/661 성공, 에러 0(20.9분 소요).

## 2. tunebat 재검증 — 자체 파이프라인(`est_key`) 개선 확인

report/06 §2에서 불일치했던 5곡을 재확인(대조군: `audio_feats.csv`의 `est_key`, 버그 수정
전/후 비교):

| 곡 | tunebat 실제 | 수정 전 `est_key` | 수정 후 `est_key` | 판정 |
|---|---|---|---|---|
| flame of hope | G major | D#min | Amin | ❌ 불일치 지속 |
| 寄る辺のSunny, Sunny | F major | Gmaj | **Fmaj** | ✅ 일치로 개선 |
| Secret Dawn | B♭ major | Dmaj | **A#maj**(=B♭ 이명동음) | ✅ 일치로 개선 |
| Angel's Ladder | B♭ major | D#min | Amin | ❌ 불일치 지속 |
| メリッサ (Cover) | A♭ major | Cmin | Cmin | ❌ 불일치 지속(변화 없음) |

기존 일치 2곡(誓いのWingbeat, 輪舞-revolution)은 그대로 A minor 일치 유지.

**결론**: 버그 수정으로 자체 파이프라인(`est_key`)의 정확도가 실측으로 개선됐다(5곡 중
2곡 신규 일치). 나머지 3곡의 불일치는 report/06 §4가 예측한 "roll 버그와 무관한 별개의
장/단조 혼동 문제"로 남아있다 — 버그 수정만으로는 완전히 해소되지 않는다는 예측이 맞았다.

## 3. 중요 발견 — `key`/`key_proxies`는 이 파이프라인 산출물이 아니다

수정 전 `est_key`와 외부 병합 컬럼(`key`, `songs_master.csv`에서 옴 / `key_proxies`,
`song_features_with_proxies.csv`에서 옴)을 나란히 비교하니, 수정 전에도 이미 서로 다른 값을
내고 있었다(예: 誓いのWingbeat — 수정 전 `est_key`=D#min인데 `key`=`key_proxies`=Amin).
즉 **`songs_master.csv`의 `key`와 `song_features_with_proxies.csv`의 `key_proxies`는 이
저장소의 `extract_features.py`/`estimate_key()`로 생성되는 값이 아니다** — 완전히 별도의
외부 계통이다.

git 히스토리 확인 결과 `data/song_features_with_proxies.csv`와 `data/songs_master.csv`의
`key` 컬럼은 커밋 `83cdf9a`("songs_master.csv 생성 — 데이터팀 완료")에서 통째로 들어온
외부 산출물이며, 이 저장소 안에는 이를 생성하는 스크립트가 없다(report/06 §6의 미해결
질문에 대한 답 — "같은 버그를 공유하는 별도 계산인지 확인" 자체가 불가능하다는 뜻. 소스
코드가 없으므로 알고리즘을 비교할 수 없다. 값 대조로만 간접 확인 가능하며, 위 표가 그
간접 확인 결과다).

## 4. 결정 — `songs_master.csv` 반영 보류

수정된 `est_key`를 프로덕션이 실제로 쓰는 `songs_master.csv`의 `key` 컬럼에 병합하는 안을
검토했으나, **연구자 판단으로 보류**했다. `songs_master.csv`는 `main`이 아닌 별도 `data`
브랜치에서 백엔드가 런타임 fetch하는 프로덕션 데이터라(memory: `live-data-branch-fetch`),
이 파일을 바꾸는 것은 연구 범위를 넘어서는 배포 영향이 있다. 이번 세션은 **연구 종결**로
마무리하고, 실제 반영 여부·방식(`key`만? `key_proxies`도?)은 별도 논의로 넘긴다.

## 5. 산출물
- 코드: `config.py`의 `KS_PROFILES` 수정 (report/06에서 이미 완료, 변경 없음)
- 데이터: `topic/audio_feats_analysis/out/audio_feats.csv` 재산출(661행, `est_key` 갱신
  반영). 수정 전 원본은 `audio_feats.csv.bak_prebugfix`, `progress.json.bak_prebugfix`로
  보존.
- **미반영**: `data/songs_master.csv`(`key` 컬럼), `data/song_features_with_proxies.csv`
  (`key_proxies` 컬럼) — 위 §4 사유로 그대로 둠.

## 6. 다음 세션에 남기는 것
- `songs_master.csv`/`key_proxies` 반영 여부는 여전히 미결정 — 필요 시 이 리포트 §2 표를
  근거로 재논의.
- report/06 §7-3(잔여 장/단조 혼동, Essentia 검증)은 이번 세션에서 다루지 않음 — 여전히
  미착수 상태로 남아있음.
