# audio_feats.csv 컬럼 메타데이터

`audio_feats.csv`(661행, 103컬럼)의 각 컬럼이 무엇을 뜻하는지 정리한다. 조인 키는 `idx`(전역
고유 정수, 0~661)이며 `tag`(`{band}__{idx:03d}`)와 1:1 대응한다.

## ⚠️ 사용 전 주의사항

- **`energy`, `energy_proxy`, `energy_proxy_proxies`는 신호가 없거나 부호가 역전되어 있어 신뢰
  불가** — `energy_full`만 유효한 에너지 지표다. 자세한 내용은 `topic/` 상위 연구 기록(음향 지표
  감사) 참조.
- **`mode_score`(및 `mode_score_proxies`)는 장조/단조 여부만 나타내며 valence(밝음/어두움 정서)와
  다르다.**
- **`est_key`, `pct_major`, `chord_change_rate`, `borrowed_chord_rate`는 24개 장/단 3화음
  템플릿 매칭(diminished 코드 없음) 기반이라 근본적으로 노이즈가 있다** — `topic/chord_progression/`
  파일럿에서 이미 자동판정 NO-GO로 결론난 것과 동일한 알고리즘이므로, 청취 검증 없이 단정하지 않는다.
- 동일 성격의 피쳐가 여러 출처에 중복 존재한다(예: `centroid`/`cen_mean`, `contrast`/`contrast_mean`,
  `tempo_excerpt`/`tempo_excerpt_proxies`) — 각각 다른 파이프라인(스니펫 vs 전체곡 등)에서 나온
  값이라 수치가 정확히 같지 않을 수 있다.

## 산출 방법 (재현 안내)

### 신규 추출 피쳐 — `src/method-1/extract_features.py`
- **오디오 로딩**: 형제 프로젝트 `bandori-song-sorter`의 `src/content/cluster/audio_full/{tag}.wav`(661곡, 곡 전체 mix)를 `librosa.load(path, sr=22050, mono=True)`로 로드.
- **`lufs`**: `pyloudnorm.Meter(sr).integrated_loudness(y)` — ITU-R BS.1770 통합 러프니스.
- **`mfcc_*_mean`/`mfcc_*_std`**: `librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)` 계산 후 시간축(axis=1) 기준 mean/std.
- **`tempo_bpm`, `n_beats`, `est_key`, `pct_major`, `chord_change_rate`, `borrowed_chord_rate`**:
  1. `librosa.feature.chroma_cqt(y, sr)`로 프레임별 12차원 크로마 추출.
  2. `librosa.onset.onset_strength` → `librosa.beat.beat_track`으로 비트 시각(및 `tempo_bpm`) 추정.
  3. 비트 구간별 크로마를 평균해 비트 단위 크로마 시퀀스로 축약.
  4. 24개 장/단 3화음 템플릿(`config.py`의 `ALL_CHORD_TEMPLATES`, 근음+장/단3도+완전5도 이진 벡터)과 코사인 유사도로 비트별 코드 판정.
  5. 곡 전체 평균 크로마와 Krumhansl-Schmuckler 12조성×2(장/단) 프로파일(`KS_PROFILES`)의 피어슨 상관으로 `est_key` 추정.
  6. `pct_major`=장조 판정 비트 비율, `chord_change_rate`=분당 코드 변경 횟수, `borrowed_chord_rate`=추정 키의 다이아토닉 풀(`DIATONIC_POOLS`)에 없는 코드 비트 비율.
  - 이 로직은 `topic/chord_progression/02_extract_chords.py`·`03_compute_features.py`의 검증된 알고리즘을 그대로 이식한 것이다(코드 자체는 독립적으로 재작성, 상수/알고리즘은 동일).
- **재현**: `cd topic/audio_feats-analysis/src/method-1 && python extract_features.py` (idempotent, `out/progress.json` 기준 이어서 처리).

### `songs_master.csv`/`full_audio_features.csv`/`song_features_with_proxies.csv` 유래 컬럼
- 이번 작업에서 새로 계산한 것이 아니라, `data/` 브랜치 스냅샷에 이미 존재하던 값을 `idx`(전역 고유 정수) 기준으로 그대로 가져와 붙인 것이다.
- 각 CSV를 실제로 산출한 원본 스크립트(`build_master.py`, `extract_full_energy.py`, `extract_temporal_intensity.py` 등으로 추정)는 이 저장소의 다른 브랜치/워크트리 히스토리에 있고 `research` 브랜치 현재 시점에는 포함되어 있지 않다 — 정확한 재현이 필요하면 해당 스크립트의 원본 커밋을 먼저 찾아야 한다.
- 병합 자체의 재현: `topic/audio_feats-analysis/src/method-1/extract_features.py` 실행 시 병합 단계가 함께 수행된다(`idx` 컬럼으로 3개 CSV를 left-merge).

### 형제 프로젝트(bandori-song-sorter) pulse 컬럼 — `src/method-1/merge_pulse.py`
- **원본 산출**(bandori-song-sorter 저장소, 이 저장소 밖의 별도 로컬 프로젝트):
  1. `src/tools/cluster/separate_drums.py <band> <idx>` — demucs(htdemucs)로 `audio_full/{tag}.wav`에서 드럼 스템만 분리해 `audio_drums/{tag}.wav` 생성(CPU 추론, 곡당 수 분).
  2. `src/tools/cluster/build_beat_track.py <band> <idx>` — 드럼 스템에서 `librosa.beat.beat_track`으로 base tempo 추정 후, onset-envelope 자기상관(ACF)을 base와 그 ×2에서 비교(`ratio = ACF(fast)/ACF(slow)`, `ratio ≥ tau=0.96`이면 빠른 pulse 채택)해 `pulse_bpm`/`pulse_div`/`ratio`/`acf_slow`/`acf_fast`를 계산, `onsets/{tag}.json`으로 저장.
  3. 상세 배경·검증 과정은 `bandori-song-sorter/docs/research/pulse-onset-extraction.md` 참조.
- **병합**: `topic/audio_feats-analysis/src/method-1/merge_pulse.py`가 `onsets/{tag}.json`을 읽어 `tag` 기준으로 `audio_feats.csv`에 좌측 조인(기존 660여 곡 커버, 분석 시점 이후 추가된 신곡은 개별적으로 위 1~2단계를 다시 실행해 채워야 함).
- **재현**: `bandori-song-sorter` 저장소 루트에서 1~2단계 스크립트 실행 → `bandori-playlist-maker` 저장소의 `topic/audio_feats-analysis/src/method-1/merge_pulse.py` 재실행.

## 식별자 컬럼

| 컬럼 | 출처 | 의미 |
|---|---|---|
| `status` | 신규 추출 | 이번 추출 파이프라인의 처리 상태(성공/스킵/에러)를 나타낸다. |
| `tag` | 신규 추출 | `{band}__{idx}` 형식의 곡 고유 식별 태그다. |
| `band` | 신규 추출 | 곡을 연주한 밴드 이름이다. |
| `song` | 신규 추출 | 곡 제목이다. |
| `idx` | songs_master | 앱 백엔드가 실제로 쓰는 전역 고유 정수 ID다(카탈로그 전체 기준 0~661). |
| `band_master` / `song_master` | songs_master | songs_master.csv 쪽 band/song 원본 값이다(조인 검증용). |
| `url` | songs_master | 곡의 유튜브 URL이다. |
| `video_id` | songs_master | 앱이 재생/현재곡 조회에 실제로 쓰는 유튜브 영상 ID다. |
| `band_audio` / `song_audio` | full_audio_features | full_audio_features.csv 쪽 band/song 원본 값이다(조인 검증용). |
| `band_proxies` / `song_proxies` | song_features_with_proxies | song_features_with_proxies.csv 쪽 band/song 원본 값이다(조인 검증용). |

## 신규 추출 피쳐 (이번 작업에서 처음 계산)

| 컬럼 | 의미 |
|---|---|
| `lufs` | ITU-R BS.1770 표준 통합 러프니스(음량) 값이다. |
| `mfcc_1_mean` ~ `mfcc_13_mean` | 13개 MFCC(멜 켑스트럼 계수) 각각의 곡 전체 평균값으로, 음색 특성을 나타낸다. |
| `mfcc_1_std` ~ `mfcc_13_std` | 13개 MFCC 각각의 곡 전체 표준편차로, 음색이 시간에 따라 얼마나 변하는지를 나타낸다. |
| `tempo_bpm` | librosa 비트 트래킹으로 추정한 곡의 템포(BPM)다. |
| `n_beats` | 코드 추출 과정에서 검출된 비트 개수다. |
| `est_key` | 크로마와 Krumhansl-Schmuckler 프로파일 상관으로 추정한 곡의 전역 조성이다. |
| `pct_major` | 전체 비트 중 장조 코드로 판정된 비트의 비율이다. |
| `chord_change_rate` | 분당 코드 변경 횟수로, 화성 진행의 빠르기(harmonic rhythm)를 나타낸다. |
| `borrowed_chord_rate` | 추정된 키의 다이아토닉 코드 풀에 속하지 않는 코드(차용/모달 믹스처)의 비율이다. |

## songs_master.csv 유래 (기존 산출 피쳐)

| 컬럼 | 의미 |
|---|---|
| `key` | songs_master 파이프라인이 추정한 곡의 조성이다. |
| `camelot` | DJ 믹싱에서 쓰는 카멜롯 표기법으로 변환한 조성 코드다. |
| `tempo_excerpt` | 곡의 일부 구간(스니펫)만으로 추정한 템포다. |
| `energy_proxy` | ⚠️ 부호가 역전된 것으로 확인된 에너지 대리 지표다(신뢰 불가). |
| `mode_score` | ⚠️ 장조/단조 여부를 나타내는 값이며 정서적 밝기(valence)가 아니다. |
| `acousticness_proxy` | 곡이 어쿠스틱(비전자음향)한 정도를 나타내는 대리 지표다. |
| `instrumentalness_proxy` | 곡이 보컬 없이 악기 위주인 정도를 나타내는 대리 지표다. |
| `bpm` | songs_master가 최종 채택한 템포(BPM) 값이다. |
| `energy` | ⚠️ 신호가 없는 것으로 확인된 에너지 컬럼이다(신뢰 불가). |
| `shape` | 곡의 정성적 분류 라벨(예: neutral, bright)이다. |
| `eligible_band` | 이 곡이 분석 대상 밴드 목록에 포함되는지 여부다. |
| `energy_full` | ✅ 곡 전체 기준으로 계산되어 신뢰 가능한 에너지 지표다. |
| `i_mean` | 곡 전체 구간의 시간적 강도(intensity) 평균값이다. |
| `i_std` | 곡 전체 구간의 시간적 강도 표준편차다. |
| `i_max` | 곡 전체 구간에서 시간적 강도의 최댓값이다. |
| `i_min` | 곡 전체 구간에서 시간적 강도의 최솟값이다. |
| `i_start` | 곡 시작 구간의 시간적 강도 값이다. |
| `i_end` | 곡 종료 구간의 시간적 강도 값이다. |

## full_audio_features.csv 유래 (기존 산출 피쳐)

| 컬럼 | 의미 |
|---|---|
| `duration_sec` | 오디오 파일의 전체 길이(초)다. |
| `cen_mean` | 스펙트럴 센트로이드(음색의 밝기)의 곡 전체 평균값이다. |
| `cen_p90` | 스펙트럴 센트로이드의 90번째 백분위수 값이다. |
| `roll_mean` | 스펙트럴 롤오프(에너지가 몰린 주파수 상한)의 평균값이다. |
| `roll_p90` | 스펙트럴 롤오프의 90번째 백분위수 값이다. |
| `bw_mean` | 스펙트럴 대역폭(주파수 분포의 퍼짐 정도)의 평균값이다. |
| `bw_p90` | 스펙트럴 대역폭의 90번째 백분위수 값이다. |
| `flat_mean` | 스펙트럴 평탄도(음색이 노이즈에 가까운 정도)의 평균값이다. |
| `flat_p90` | 스펙트럴 평탄도의 90번째 백분위수 값이다. |
| `contrast_mean` | 스펙트럴 대비(주파수 대역 간 두드러짐 차이)의 평균값이다. |
| `contrast_p90` | 스펙트럴 대비의 90번째 백분위수 값이다. |
| `zcr_mean` | 영교차율(zero-crossing rate, 신호가 거칠거나 타악기적인 정도)의 평균값이다. |
| `zcr_p90` | 영교차율의 90번째 백분위수 값이다. |
| `perc_mean` | 타악기(percussive) 성분 강도의 평균값이다. |
| `perc_p90` | 타악기 성분 강도의 90번째 백분위수 값이다. |
| `perc_p95` | 타악기 성분 강도의 95번째 백분위수 값이다. |
| `onset_mean` | 온셋(음의 시작) 강도의 평균값이다. |
| `onset_p90` | 온셋 강도의 90번째 백분위수 값이다. |
| `onset_rate` | 초당 온셋 발생 빈도다. |
| `rms_mean` | RMS 에너지(음량)의 평균값이다. |
| `rms_p90` | RMS 에너지의 90번째 백분위수 값이다. |
| `extract_sec` | 이 피쳐를 추출하는 데 걸린 처리 시간(초)이다. |
| `error` | 추출 과정에서 에러가 발생했다면 그 메시지가 담긴다(정상 처리 시 비어있음). |

## song_features_with_proxies.csv 유래 (기존 산출 피쳐)

| 컬럼 | 의미 |
|---|---|
| `duration_s` | 오디오 파일의 전체 길이(초)다. |
| `harmonic_ratio` | 전체 신호 중 하모닉(음정이 있는) 성분이 차지하는 비율이다. |
| `centroid` | 이 파이프라인에서 별도로 계산한 스펙트럴 센트로이드 값이다. |
| `rolloff` | 이 파이프라인에서 별도로 계산한 스펙트럴 롤오프 값이다. |
| `flatness` | 이 파이프라인에서 별도로 계산한 스펙트럴 평탄도 값이다. |
| `contrast` | 이 파이프라인에서 별도로 계산한 스펙트럴 대비 값이다. |
| `flux` | 스펙트럴 플럭스(주파수 스펙트럼이 프레임 간 변화하는 정도)다. |
| `zcr` | 이 파이프라인에서 별도로 계산한 영교차율 값이다. |
| `rms` | 이 파이프라인에서 별도로 계산한 RMS 에너지 값이다. |
| `tempo_excerpt_proxies` | 이 파이프라인에서 스니펫 기준으로 추정한 템포 값이다. |
| `mode_score_proxies` | ⚠️ 이 파이프라인에서 계산한 장조/단조 점수이며 valence가 아니다. |
| `key_proxies` | 이 파이프라인에서 추정한 곡의 조성이다. |
| `voiced_frac_mix` | 믹스 오디오에서 유성음(보컬 등 음정 있는 발성) 구간이 차지하는 비율이다. |
| `acousticness_proxy_proxies` | 이 파이프라인에서 계산한 어쿠스틱함 정도의 대리 지표다. |
| `instrumentalness_proxy_proxies` | 이 파이프라인에서 계산한 악기 위주 정도의 대리 지표다. |
| `energy_proxy_proxies` | ⚠️ 부호가 역전된 것으로 확인된 에너지 대리 지표다(신뢰 불가). |

## 형제 프로젝트(bandori-song-sorter) pulse 분석 유래

| 컬럼 | 의미 |
|---|---|
| `drum_tempo_bpm` | 드럼 스템만 분리해 추정한 템포로, 전체 믹스 기준 `tempo_bpm`과 다를 수 있다. |
| `pulse_bpm` | 형제 프로젝트가 최종 채택한 지각적 pulse 템포(체감 속도)다. |
| `pulse_div` | 채택된 pulse의 세분화 수준이다(1=박/느림, 2=8분/빠름). |
| `pulse_ratio` | 빠른 옥타브(×2)와 느린 옥타브의 onset ACF 비율로, 값이 높을수록(0.96 이상) 빠른 pulse가 두드러진다는 뜻이다. |
| `pulse_acf_slow` | 느린 옥타브 후보의 onset 자기상관 원값이다. |
| `pulse_acf_fast` | 빠른 옥타브 후보의 onset 자기상관 원값이다. |
| `pulse_tau` | 빠른 pulse 채택 여부를 가르는 임계값(형제 프로젝트에서 0.96으로 튜닝됨)이다. |

### 주의: 템포 vs Pulse
원본 `tempo_bpm`(전체 믹스, librosa beat_track)과 이 pulse 값들은 서로 다른 목적으로 설계되었다. `tempo_bpm`은 음향적으로 정확한 템포를 추정하는 반면, pulse 값들은 같은 bpm이라도 드럼 편곡 밀도에 따라 달라지는 **체감 속도(지각적 pulse rate)**를 나타낸다. 따라서 직접 비교보다는 상호보완적으로 활용하기를 권장한다.
