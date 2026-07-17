# 화성학적 코드진행 → valence 대리축 파일럿 실험 설계서

> **목적**: 지금까지 세 갈래 연구([[vector-embedding Phase 2 §9]], `mood_warmth` 1·2라운드)가 공통으로
> 부딪힌 병목 — "이 카탈로그엔 검증된 valence(밝음↔슬픔) 축이 없다. `mode_score`는 장/단조일 뿐"
> — 을 코드진행(화성) 기반 지표로 뚫을 수 있는지 **소규모 파일럿**으로 먼저 검증한다.
> 본격 661곡 확장 전에, 코드 인식 자체가 이 장르(왜곡 기타·메탈 포함)에서 신뢰할 만한지와
> valence 신호가 실제로 있는지를 싸게 먼저 본다.
>
> **구현자는 이 문서만 보고 코드를 작성한다** — 결정(재료·지표·판정 기준)을 임의로 바꾸지 말고
> 막히면 질문할 것.

---

## 0. 연구 질문과 판정 기준 (사전 등록 — 결과를 본 뒤 변경 금지)

**RQ**: 코드진행에서 유래한 지표가 (a) `mode_score`만큼 또는 그 이상으로 bright/dark 정답
라벨을 분리하는가, 그리고 (b) `mode_score`가 명백히 틀렸던 **알려진 반례**를 바로잡는가?

**알려진 반례 (§1b, `report/02-acoustic_feature_audit.md` / `method-2/DESIGN.md` §1b)**:

| 곡 | 사용자 평가 | `mode_score` 백분위 |
|---|---|---|
| poppin_party `Yes! BanG_Dream!` | 매우 밝음(10점) | 0.04 (최암부) |
| hello_happy_world `Happy! Happier! Happiest!`류 2곡 | 밝음(9~10점) | 0.24 / 0.39 |

이 3곡은 J-rock 특유의 "단조인데 밝고 신나는" 사례로 이미 지목돼 있다. 코드진행 지표가
이들을 "밝음" 쪽으로 옮긴다면 mode_score보다 우월하다는 직접 증거다.

| 판정 | 조건 |
|---|---|
| **GO (661곡 확장)** | 후보 지표 중 하나 이상이 16곡 bright/dark 분리에서 `mode_score`와 동등하거나 더 나은 효과크기를 보이고, **AND** 위 3개 반례 중 2개 이상을 "밝음" 쪽으로 올바르게 재분류 |
| **조건부** | 분리력은 개선했으나 반례 교정은 부분적(1/3) → 코드 인식 품질부터 재점검 후 재시도 |
| **NO-GO** | 어느 후보 지표도 mode_score 대비 개선 없음, 또는 반례 교정 0/3 → 이 방향 폐기, `mood_warmth` valence 트랙으로 자원 집중 |

**사전 선언한 한계** (결과와 무관하게 보고서에 유지):
- n=16(정답 라벨) + 3(반례) = 19곡. **확증이 아니라 방향성 탐색**이다.
- 코드 인식(chroma+템플릿 매칭)은 클래식 화성 분석용 도구를 밴드 록/메탈에 적용하는 것이라
  정확도가 검증되지 않았다 — §4에서 **육안 대조 스팟체크**를 반드시 포함한다.
- roselia·ave_mujica(dark 라벨 6/8)는 메탈이라 디스토션 기타의 배음이 크로마를 오염시킬 수 있다.

---

## 1. 재료 — `no_vocals.wav`를 쓴다 (보컬 아님)

**결정**: 화성(코드)은 동시에 울리는 여러 음의 조합이며, 보컬은 단선율(monophonic)이라
원리적으로 코드진행을 담을 수 없다. 코드는 반주(기타/베이스/키보드)가 쥐고 있다.

`topic/vector-embedding/src/method-1/work/stems_full/htdemucs/<tag>/no_vocals.wav`를 쓴다
(2-stem 분리, `vocals.wav`+`no_vocals.wav`만 존재 — 4-stem 아님, 확인됨). 보컬이 제거된
반주 트랙이라 풀 믹스보다 크로마 특징이 깨끗하다. 재분리 필요 없음(661곡 전부 이미 존재).

**절대 `vocals.wav`를 코드 추출에 쓰지 말 것** — 이론적으로 틀린 접근이다.

---

## 2. 대상 곡 (19곡)

- `data/ground_truth_labels.csv`에서 `dimension == "brightness"`인 16행(bright 8 / dark 8).
- 반례 3곡(§0 표) — `idx`로 `songs_master.csv`(또는 `full_catalog_songs.csv`)에서 `tag` 조회.
- 산출물 `out/pilot_song_list.csv`: `tag, band, song, label(bright/dark/mismatch_known)`.

---

## 3. 코드 추출 방법

새 무거운 의존성(딥러닝 코드 인식 모델) 도입 없이, **크로마 + 템플릿 매칭**으로 간다.
파일럿 규모(19곡)에 적합하고, 실패해도 비용이 작다.

1. `librosa.load(no_vocals.wav, sr=22050)` → `librosa.feature.chroma_cqt`로 프레임별 12차원
   크로마 벡터 추출.
2. 비트 추적(`librosa.beat.beat_track`)으로 비트 경계를 잡고, 비트 단위로 크로마를 평균해
   프레임 수를 줄인다(비트당 1개 크로마 벡터 — 화성 리듬 분석의 표준 단위).
3. **24개 템플릿**(장3화음 12개 + 단3화음 12개, 표준 이진 템플릿: 근음·3음·5음=1, 나머지=0)과
   각 비트 크로마의 코사인 유사도를 계산, 최댓값 템플릿을 그 비트의 코드로 배정.
4. 인접한 동일 코드는 병합해 `(코드, 시작비트, 지속비트)` 시퀀스로 저장.
5. 전역 조성(key)은 Krumhansl-Schmuckler 프로파일과 곡 전체 평균 크로마의 상관으로 추정
   (24개 중 최댓값).

산출물 `out/chord_sequences.csv`: `tag, beat_idx, chord_root, chord_quality(major/minor), confidence`.

---

## 4. 후보 valence 지표 (사전 등록 — 이 3개만, 사후 추가 금지)

| 지표 | 정의 | 가설 |
|---|---|---|
| `pct_major` | major 코드로 배정된 비트 비율 | 장조 코드 비중이 높을수록 밝음(단, mode_score와 유사해 개선 안 될 수도 있음 — 대조 목적) |
| `chord_change_rate` | 분당 코드 변화 횟수(화성 리듬) | 변화가 빠를수록 활기/긴장감(밝음과는 다른 축일 수 있음 — 탐색적) |
| `borrowed_chord_rate` | 추정 전역 조성의 다이어토닉 7개 코드에 **속하지 않는** 코드의 비율 (모달 믹스처·이차 딸림화음) | J-rock이 단조 진행이라도 장조 색채 코드(borrowed major chord)를 섞어 "밝게" 들리게 하는 경우를 포착 — **mode_score가 놓치는 정확히 그 지점**을 겨냥한 핵심 후보 |

**육안 대조 스팟체크 (필수, §0 한계 대응)**: 19곡 중 최소 3곡(반례 3곡 포함)은 연구자가 직접
`out/chord_sequences.csv`를 듣고 대조해, 코드 인식이 상식적으로 말이 되는지 확인한다. 이 확인
없이 지표만 믿고 GO/NO-GO를 내리지 않는다.

---

## 5. 판정 절차

1. 16곡(bright/dark)에서 `mode_score`(비교 기준선, `songs_master.csv`에서 재사용)와 위 3개
   후보 지표 각각의 bright-vs-dark 분리를 계산 — **평균 차이 + Cohen's d**(mood_warmth·
   Phase2 §9 관례 승계).
2. 3개 반례에 대해 각 지표의 백분위(19곡 또는 전체 661곡 대비, 둘 다 기록)를 확인 —
   mode_score처럼 최암부/저조에 있는지, 아니면 개선됐는지.
3. §0 판정표 적용.

산출물 `out/pilot_validation.csv`: `feature, bright_mean, dark_mean, cohens_d`,
`out/pilot_mismatch_check.csv`: `tag, mode_score_pct, pct_major_pct, chord_change_rate_pct, borrowed_chord_rate_pct`.

---

## 6. 구현 산출물 (파일 목록)

`topic/chord_progression/` 아래:

| 파일 | 역할 |
|---|---|
| `config.py` | 경로·SEED(20260717 승계)·템플릿 정의 |
| `01_select_pilot_songs.py` | §2 — `out/pilot_song_list.csv` |
| `02_extract_chords.py` | §3 — `out/chord_sequences.csv` (진행률 JSON: `out/chord_progress.json`) |
| `03_compute_features.py` | §4 — `out/chord_features.csv` (`tag, pct_major, chord_change_rate, borrowed_chord_rate, est_key`) |
| `04_validate.py` | §5 — `out/pilot_validation.csv`, `out/pilot_mismatch_check.csv` |
| `README.md` | 실행법 |

**공통 규칙**: idempotent(있으면 스킵), `conda env warmth`의
`C:/Users/User/miniconda3/envs/warmth/python.exe` 직접 호출 + `PYTHONIOENCODING=utf-8`
(`conda run` 금지 — cp949 크래시, 기존 세션 규칙 승계).

## 7. 실행 순서

```
01_select_pilot_songs.py → 19곡 목록 확인
02_extract_chords.py     → 코드 시퀀스 (연구자 3곡 스팟체크)
03_compute_features.py   → 후보 지표 3개
04_validate.py           → 분리력 + 반례 교정 여부
  ↓
§0 판정 → GO면 661곡 확장 설계, NO-GO면 종료 기록
```
