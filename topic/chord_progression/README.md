# 화성학적 코드진행 → valence 대리축 파일럿 실험

## 개요

DESIGN.md에 따른 코드진행 기반 밝음/어두움(valence) 지표 파일럿.

**목표**: 기존 `mode_score`가 놓치는 J-rock의 "단조인데 밝은" 사례를 코드진행 지표로 포착할 수 있는지 검증.

**대상**: 16곡(bright/dark 각 8곡) + 반례 3곡 = 19곡

**산출물**:
- `out/pilot_song_list.csv` — 19곡 목록
- `out/chord_sequences.csv` — 비트 단위 코드 시퀀스
- `out/chord_progress.json` — 진행 추적 (idempotent)
- `out/chord_features.csv` — 3개 후보 지표
- `out/pilot_validation.csv` — 효과크기(Cohen's d) 비교
- `out/pilot_mismatch_check.csv` — 반례 3곡 백분위

---

## 실행 방법

### 필수 환경

- **Python 환경**: `warmth` conda env (librosa, scipy, pandas, numpy 포함)
- **오디오 파일**: `topic/vector_embedding/src/method-1/work/stems_full/htdemucs/<tag>/no_vocals.wav` (2-stem 분리 완료)
- **라벨 데이터**: `data/ground_truth_labels.csv`, `data/songs_master.csv`

### 단계별 실행

#### 1. 파일럿 곡 선택

```powershell
# Windows PowerShell
$env:PYTHONIOENCODING = "utf-8"
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 01_select_pilot_songs.py
```

또는 Bash:
```bash
export PYTHONIOENCODING=utf-8
C:/Users/User/miniconda3/envs/warmth/python.exe 01_select_pilot_songs.py
```

**출력**: `out/pilot_song_list.csv` (19곡 목록)

#### 2. 코드 추출 (시간 소요)

```powershell
$env:PYTHONIOENCODING = "utf-8"
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 02_extract_chords.py
```

**소요 시간**: ~5-10분 (19곡, GPU/CPU 성능에 따라)
**출력**:
- `out/chord_sequences.csv` — 비트 단위 코드 (건너뛴다면 ~1000-2000 행)
- `out/chord_progress.json` — 진행 메타데이터 (idempotent 추적용)

**진행 중단 & 재개**: `chord_progress.json`이 있으면 이미 처리한 곡은 스킵함.

#### 3. 지표 계산

```powershell
$env:PYTHONIOENCODING = "utf-8"
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 03_compute_features.py
```

**출력**: `out/chord_features.csv` (19곡 × 4 컬럼: tag, pct_major, chord_change_rate, borrowed_chord_rate, est_key)

#### 4. 검증 & 판정

```powershell
$env:PYTHONIOENCODING = "utf-8"
& 'C:/Users/User/miniconda3/envs/warmth/python.exe' 04_validate.py
```

**출력**:
- `out/pilot_validation.csv` — 16곡(bright/dark)에서 각 지표의 bright-vs-dark 분리력(Cohen's d)
- `out/pilot_mismatch_check.csv` — 반례 3곡이 전체 19곡 중 몇 번째 백분위에 있는지

---

## 중요 설계 결정 (DESIGN.md)

### 1. no_vocals.wav만 사용 (vocals.wav 금지)

**이유**: 코드(화성)는 동시에 울리는 여러 음의 조합이므로 반주에서만 추출 가능. 보컬은 단선율로 코드 정보가 없음.

### 2. 크로마 + 비트 추적 + 템플릿 매칭

**절차**:
1. librosa 크로마_cqt (튜닝 로버스트) 추출
2. beat_track()로 비트 경계 추정
3. 비트 단위로 크로마 평균
4. 24개 템플릿(major 12 + minor 12) 코사인 유사도 매칭
5. 인접 동일 코드 병합
6. Krumhansl-Schmuckler 프로파일로 전역 조성 추정

**선택 이유**: 새로운 딥러닝 모델 도입 없이, 경량 파일럿에 적합.

### 3. 3개 지표만 (사후 추가 금지)

| 지표 | 정의 | 가설 |
|---|---|---|
| `pct_major` | major 코드 비율 | 장조 색채 ↔ 밝음 (mode_score와 유사할 수도) |
| `chord_change_rate` | 분당 코드 변화 횟수 | 빠른 화성 리듬 ↔ 활기/긴장감 |
| `borrowed_chord_rate` | 추정 key의 다이어토닉 7개 외 코드 비율 | **핵심**: J-rock의 "단조인데 장조 코드 섞음" 포착 |

### 4. 검증 기준 (DESIGN.md §0)

| 판정 | 조건 |
|---|---|
| **GO** | 후보 지표 ≥1개가 mode_score 수준의 효과크기(Cohen's d) + 반례 3곡 중 ≥2개를 "밝음" 방향으로 재분류 |
| **조건부** | 분리력 개선 O, 반례 교정 부분적(1/3) → 코드 인식 재점검 후 재시도 |
| **NO-GO** | 어느 지표도 개선 없음 또는 반례 교정 0/3 → 이 방향 폐기 |

---

## 코드 구조

```
topic/chord_progression/
├── config.py                  # 경로, SEED, 24개 템플릿, K-S 프로파일, 다이어토닉 풀
├── 01_select_pilot_songs.py   # 라벨 로드 → 19곡 선택
├── 02_extract_chords.py       # 오디오 처리 → 비트 단위 코드 시퀀스
├── 03_compute_features.py     # 코드 시퀀스 → 3개 지표
├── 04_validate.py             # 효과크기 + 반례 백분위 계산
├── README.md                  # (이 파일)
└── out/
    ├── pilot_song_list.csv              # 19곡
    ├── chord_sequences.csv              # 비트 수준
    ├── chord_progress.json              # idempotent 메타
    ├── chord_features.csv               # 3개 지표
    ├── pilot_validation.csv             # bright/dark 분리력
    └── pilot_mismatch_check.csv         # 반례 백분위
```

---

## 알려진 한계 (DESIGN.md §0)

1. **표본 크기**: n=16(정답) + 3(반례) = 19곡. 방향성 탐색이지 확증이 아님.
2. **코드 인식 정확도**: 클래식 화성 분석용 chroma+템플릿 매칭을 밴드 록/메탈에 적용. 검증 필수.
3. **디스토션 기타**: roselia·ave_mujica의 메탈 사운드는 배음 오염 가능.

**필수 QC**: 19곡 중 최소 3곡(반례 3곡 포함)은 `chord_sequences.csv`를 직접 듣고 검증.

---

## 문제 해결

### "ImportError: No module named librosa"

→ warmth 환경에 설치 필요. 단, 이 스크립트는 설치하지 않음. 연구자가 별도로 환경 세팅.

### "PYTHONIOENCODING=utf-8 없으면 한글 크래시"

→ Windows cp949 인코딩 호환성. README의 실행 예시처럼 반드시 environment variable 설정.

### "Audio not found at ..."

→ stems_full 디렉토리 확인. `topic/vector_embedding/src/method-1/work/stems_full/htdemucs/<tag>/no_vocals.wav` 경로 확인.

### 중단 후 재개

→ `chord_progress.json`이 자동 생성됨. 재실행 시 이미 처리한 곡은 스킵.

---

## 다음 단계 (GO 판정 시)

1. 661곡 전체 확장 설계 (리소스·시간 재검토)
2. 코드 인식 정확도 벤치마크 (육안 대조 확대)
3. borrowed_chord_rate 외 추가 지표 탐색
