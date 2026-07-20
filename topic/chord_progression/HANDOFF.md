# chord_progression 인수인계 — 다른 세션(메인 로컬)에서 이어받기

> 작성 시점: 2026-07-18. 이 문서만 보고 이어서 진행할 수 있도록 현재 상태·산출물·다음 단계를
> 정리한다. 설계 원본은 `DESIGN.md`(사전 등록, 변경 금지) 참조.

## 현재 상태 요약

**파이프라인(01~04) 전부 실행 완료.** 자동 판정 기준으로는 **NO-GO**가 나왔으나, DESIGN.md §4가
**필수로 요구한 육안·청취 스팟체크(최소 3곡)를 아직 수행하지 않았다** — 이 문서를 이어받는 세션의
할 일은 그 스팟체크와 최종 보고서 작성이다.

## 이미 완료된 것

1. `01_select_pilot_songs.py` → `out/pilot_song_list.csv` — 19곡(bright 8 + dark 8 + 반례 3) 확정.
   반례 3곡은 mode_score **백분위**(0.04/0.24/0.39)로 정확히 대조 검증됨(곡명 추측이 아님 — 최초
   구현에 있던 버그를 수정한 결과. `poppin_party__375`, `hello_happy_world__111`,
   `hello_happy_world__109`).
2. `02_extract_chords.py` → `out/chord_sequences.csv`(9,330 비트 단위 코드 레코드, 19곡 전체).
   실행 중 librosa 버전 차이로 인한 버그 2건을 고쳤다(`beat_track`의 `onset_strength`→
   `onset_envelope` 키워드 변경, `tempo`가 스칼라가 아니라 1원소 ndarray로 반환되는 문제) — 코드
   자체(`02_extract_chords.py`)에 이미 반영돼 있으니 재실행 시 문제 없다.
3. `03_compute_features.py` → `out/chord_features.csv` — 19곡 × 3개 사전등록 지표
   (`pct_major`, `chord_change_rate`, `borrowed_chord_rate`) + 추정 조성(`est_key`).
4. `04_validate.py` → `out/pilot_validation.csv`, `out/pilot_mismatch_check.csv` — 최종 판정 계산.

## 자동 판정 결과 (사전등록 기준 그대로 적용)

| 지표 | Cohen's d (bright vs dark, n=8/8) |
|---|---|
| **mode_score**(기준선) | **15.49** |
| pct_major | 0.96 |
| chord_change_rate | 0.09 |
| borrowed_chord_rate | 0.15 |

- 어떤 코드진행 지표도 mode_score의 분리력을 따라잡지 못함.
- 반례 3곡 재분류: `poppin_party__375`("Yes! BanG_Dream!")·`hello_happy_world__111`("にこ×にこ")는
  어떤 지표로도 밝음 방향 신호 없음(✗). `hello_happy_world__109`("えがお･シング･あ･ソング")만
  borrowed_chord_rate가 19곡 중 최상위(100th pct)로 나와 "개선 가능성"(✓) — **1/3만 교정**.
- DESIGN.md §0 판정표: "분리력 개선 없음" → **NO-GO**(661곡 확장 보류가 자동판정 결론).

## 다음 세션이 할 일 (순서대로)

1. **스팟체크 대상 선정 (최소 3곡, 반례 포함 권장)**: `out/chord_sequences.csv`에서 아래 후보 중
   골라 실제로 들으며 코드 인식이 상식적인지 확인.
   - 반례 3곡(위 표) — 자동 판정에서 신호가 안 잡힌 이유가 "코드 인식 자체가 틀려서"인지,
     "코드는 맞는데 지표 설계가 이 현상을 못 잡아서"인지 구분하는 게 핵심.
   - roselia·ave_mujica 중 최소 1곡(디스토션 기타 배음이 크로마를 오염시킬 수 있다고 DESIGN.md
     §0이 사전에 우려한 지점).
   - 오디오 원본: `topic/vector_embedding/src/method-1/work/stems_full/htdemucs/<tag>/no_vocals.wav`
     (2-stem 분리, 661곡 전부 이미 존재 — 재분리 불필요).
   - 대조 방법: `out/chord_sequences.csv`를 tag로 필터링해 `(beat_idx, chord_root, chord_quality,
     confidence)` 시퀀스를 곡을 들으며 눈으로/귀로 따라가거나, 필요하면 비트 타임스탬프를 별도
     계산해 특정 구간만 스팟체크해도 된다(원 스크립트가 초 단위 타임스탬프를 직접 저장하진
     않으므로, 대략적 대조로 충분 — DESIGN.md도 "정밀 검증"이 아니라 "상식적으로 말이 되는지"
     확인이라고 명시함).
2. **스팟체크 결과에 따라 최종 판정**:
   - 코드 인식이 대체로 타당해 보이면 → 자동 NO-GO를 그대로 확정, `report/01-chord_progression_pilot.md`
     작성(선택_pipeline의 `report/01-selection_pipeline_comparison.md` 형식 참고 — 판정 표,
     한계, 권고 순으로).
   - 코드 인식 자체가 심하게 틀려 보이면(특히 메탈 장르) → NO-GO를 "코드 인식 신뢰도 문제로 인한
     조건부 결론"으로 격하하고, 재시도 여부(다른 크로마 파라미터, 전용 코드인식 라이브러리 도입 등)를
     연구자와 상의.
3. 보고서 완료 시 `document-archive` 브랜치의 `archive/last-papers/research/`로 별도 커밋
   (git-rules.md `research` 절 참조 — `main`으로 가지 않음).

## 참고 — 실행 명령 (재실행 시)

```powershell
cd topic/chord_progression
$env:PYTHONIOENCODING = "utf-8"
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 01_select_pilot_songs.py
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 02_extract_chords.py   # idempotent, out/chord_progress.json 참조
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 03_compute_features.py
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 04_validate.py
```

`conda run` 금지(cp949 인코딩 크래시) — 위처럼 `python.exe` 직접 호출 + `PYTHONIOENCODING=utf-8` 필수.

## 알려진 한계 (DESIGN.md §0 원문 그대로, 변경 없음)

- n=16(정답 라벨)+3(반례)=19곡 — 확증이 아니라 방향성 탐색.
- 코드 인식(chroma+템플릿 매칭)은 밴드 록/메탈에 대한 정확도가 검증되지 않은 도구를 쓴 것이라,
  스팟체크 없이 결론을 확정하면 안 된다는 게 원 설계의 핵심 안전장치.
- roselia·ave_mujica(dark 라벨 6/8)는 메탈이라 디스토션 기타의 배음이 크로마를 오염시킬 수 있음.
