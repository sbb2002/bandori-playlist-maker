# method-2: 가사 × 음향 결합 검색 (late fusion)

## 개요

[DESIGN.md](DESIGN.md)에서 정의한 대로, Phase 1의 결론 "가사 임베딩 실패는 가사-곡조 불일치"를 받아
음향 특성을 결합해 교정되는지 검증하는 실험.

- **기본 가설**: 가사 단독(arm A)의 6쿼리 평균 5.17/10은 음향 축 결합으로 ≥7.0에 도달할 것
- **추가 기준**: "슬픈 노래"(T1-Q2, 0.3점)는 ≥5.0으로 교정되어야 함

## 파일 구조

```
method-2/
├── DESIGN.md                           # 실험 설계서 (정본)
├── README.md                           # 이 파일
├── config.py                           # 경로·상수·쿼리 정의
├── full_catalog_songs.csv              # 곡 카탈로그 (661곡)
│
├── 01_audit_features.py                # §1: 음향 지표 감사
├── 02_build_acoustics.py               # §2: 음향 축 구축 (intensity/brightness/tempo)
├── 03_query_targets.py                 # §3: LLM으로 쿼리→음향 목표 변환
├── 04_fusion_search.py                 # §4: 3 arm 검색 (가사·음향·결합)
├── 05_build_blind_sheet.py             # §5: 블라인드 평가 시트
│
├── work/                               # .gitignore
│   ├── groq.key                        # GROQ_API_KEY (절대 커밋 금지)
│   └── ...
│
└── out/                                # 산출물
    ├── feature_audit.csv               # 01의 감사표
    ├── song_acoustics.csv              # 02의 661곡 음향 프로필
    ├── query_acoustic_targets.csv      # 03의 쿼리 음향 목표
    ├── query_targets_progress.json     # 03의 진행률
    ├── phase2_search_results.csv       # 04의 3 arm 검색 결과
    ├── phase2_alpha_sensitivity.csv    # 04의 α 민감도 분석
    ├── phase2_search_progress.json     # 04의 진행률
    ├── phase2_blind_sheet.csv          # 05의 블라인드 평가 시트
    ├── phase2_blind_mapping.csv        # 05의 언블라인드 맵
    └── ...
```

## 실행 순서

### 1. 피어 검증 환경 준비

```bash
# GROQ_API_KEY 설정 (두 가지 방법 중 하나)
## 방법 1: 환경변수
export GROQ_API_KEY="..."

## 방법 2: 키 파일 (권장, method-1과 공유)
# work/groq.key 파일에 키 작성 (절대 커밋 금지)
# config.py에서 자동 로드
```

### 2. 스크립트 순차 실행

```bash
cd /c/Users/User/Documents/pyworks/bandori-playlist-maker

# 환경 변수 설정 (Windows PowerShell에서는 불필요, 이미 Bash 내 설정됨)
PYTHONIOENCODING=utf-8

# 순차 실행 (각 스크립트는 이전 산출물을 입력으로 씀)

# Step 1: 음향 지표 감사 (빠름, <1초)
/c/Users/User/miniconda3/envs/warmth/python.exe \
  topic/vector-embedding/src/method-2/01_audit_features.py

# Step 2: 음향 축 구축 (빠름, <10초)
/c/Users/User/miniconda3/envs/warmth/python.exe \
  topic/vector-embedding/src/method-2/02_build_acoustics.py

# Step 3: 쿼리→목표 변환 (LLM 호출, ~30초)
/c/Users/User/miniconda3/envs/warmth/python.exe \
  topic/vector-embedding/src/method-2/03_query_targets.py

# Step 3 이후 checkpoint: 생성된 out/query_acoustic_targets.csv를 눈으로 검토하여
# 음향 목표값이 상식적인지 (예: "자장가"→INTENSITY 낮음) 확인

# Step 4: Fusion 검색 (임베딩 + 검색, ~2-5분)
# → GPU 사용 가능하므로 빠름
/c/Users/User/miniconda3/envs/warmth/python.exe \
  topic/vector-embedding/src/method-2/04_fusion_search.py

# Step 5: 블라인드 시트 생성 (빠름, <1초)
/c/Users/User/miniconda3/envs/warmth/python.exe \
  topic/vector-embedding/src/method-2/05_build_blind_sheet.py
```

### 3. 블라인드 평가

생성된 `out/phase2_blind_sheet.csv`를 IDE에서 열어 0~10 점수를 매긴다.
- `score`: 0~10 정수
- `comment`: 선택 (청취 후 인상 기록)

**주의**: `out/phase2_blind_mapping.csv`는 평가 전까지 열지 말 것 (앵커링 위험).

### 4. 결과 분석 (구현 예정)

`06_unmask_and_report.py` (아직 구현 안 됨) — arm별 평균 → DESIGN.md §0 판정 기준 적용

---

## 파일 상세

### config.py

- `SEED = 20260717` — 재현성
- `ALPHA = 0.5` — 주 평가 가중치
- `STAGE2_QUERIES` — method-1에서 그대로 복사한 6개 쿼리 (재작성 금지)
- `get_groq_api_key()` — 키 로드 (env → work/groq.key → method-1/work/groq.key)

### 01_audit_features.py

DESIGN.md §1a의 감사 재현. 음향 지표가 정답 라벨과 매칭되는지 확인.

입력: `data/songs_master.csv`, `data/ground_truth_labels.csv`
출력: `out/feature_audit.csv`

### 02_build_acoustics.py

DESIGN.md §2: `src/backend/app/repo/song_repo.py`의 intensity 합성 로직을 정확히 이식.

```
intensity(곡) = power_mean_p3([
  percentile(-acousticness_proxy),  # 1 = 비어쿠스틱(시끄러움)
  energy_full,                       # 0~1 원값 그대로
  percentile(i_min),
  percentile(i_mean),
  percentile(i_end),
])
```

- 백분위 기준: eligible_band==True인 행만
- 결측값 자동 제외
- P = 3 (soft-OR, 하나라도 시끄러우면 시끄럽게)

입력: `data/songs_master.csv`
출력: `out/song_acoustics.csv` (661행)

### 03_query_targets.py

DESIGN.md §3: 자연어 쿼리를 LLM으로 음향 목표로 변환.

입력: `config.STAGE2_QUERIES` (6개 쿼리)
출력: `out/query_acoustic_targets.csv` (쿼리 × 3축 백분위 목표 또는 NA)

- 모델: `meta-llama/llama-4-scout-17b-16e-instruct`
- temperature: 0.0
- 캐시: 파일이 있으면 재호출 안 함

### 04_fusion_search.py

DESIGN.md §4: 3 arm 검색.

- **Arm A** (가사 단독): `lyr_rank` = percentile(cosine similarity)
  - method-1과 동일한 결과 도출
  - 베이스라인: 5.17/10
  
- **Arm B** (음향 단독): `acou_rank` = percentile(acoustic match)
  - 대조군: 가사의 기여도 측정
  
- **Arm C** (결합): `α·lyr_rank + (1-α)·acou_rank` with α=0.5
  - 주 판정 대상

민감도 분석 (참고용):
- α=0.25, α=0.75에 대한 top-3도 output
- 단, **평가·판정은 α=0.5만**

입력: `out/song_acoustics.csv`, `out/query_acoustic_targets.csv`,
       `method-1/out/stage2_queries_expanded.csv`, `method-1/out/stage2_eval_sheet.csv`

출력:
- `out/phase2_search_results.csv` (3 arm × 6 queries × top-3 = 54행)
- `out/phase2_alpha_sensitivity.csv` (참고용)

### 05_build_blind_sheet.py

DESIGN.md §5: 블라인드 평가 시트.

절차:
1. 3 arm의 (query_id, tag) 쌍 합집합 (최대 54쌍)
2. method-1에서 이미 채점된 쌍 제외 (점수 승계, 재청취 불필요)
3. 남은 쌍 무작위 셔플 (seed=20260717)
4. arm/rank/cosine 컬럼 제외 (블라인드 유지)

출력:
- `out/phase2_blind_sheet.csv` — 평가 폼 (연구자가 0~10 채움)
- `out/phase2_blind_mapping.csv` — 언블라인드 맵 (평가 후까지 미열람)

---

## 검증 체크리스트

실행 후 다음을 확인하라:

### 01 (feature_audit.csv)
- [ ] DESIGN.md §1a 표와 비교: energy_full이 intensity 분리 (loud > quiet, party > calm)

### 02 (song_acoustics.csv)
- [ ] 행 수: **661행** (전 곡)
- [ ] intensity 값: [0, 1] 범위 내
- [ ] 검증: ground_truth_labels.csv의 intensity:loud 평균 > intensity:quiet 평균

### 03 (query_acoustic_targets.csv)
- [ ] 쿼리 6개 모두 존재
- [ ] "자장가" (T3-Q2) → INTENSITY 낮음인지 확인
- [ ] "신나는 기분" (T2-Q2) → INTENSITY/TEMPO 높음인지 확인
- [ ] NA 사용이 적절한지 (예: BRIGHTNESS가 불필요하면 NA)

### 04 (phase2_search_results.csv)
- [ ] arm A top-3 (각 쿼리)가 method-1/out/stage2_eval_sheet.csv와 일치하는지 확인
  - 동일 방법이므로 정확히 일치해야 함 (불일치 = 임베딩 설정 오류)
- [ ] arm B/C도 합리적인 곡들인지 눈으로 확인

### 05 (phase2_blind_sheet.csv)
- [ ] 행 수: 대략 30~50행 (이미 채점된 쌍 제외)
- [ ] query_id/prompt_text/band/song/url 모두 채워졌는지 확인
- [ ] score/comment는 비어있는지 확인 (평가자가 채울 부분)

---

## 문제 해결

### Groq 키 오류

```
ERROR: GROQ_API_KEY not found
```

**해결**:
1. `work/groq.key` 파일 생성 (한 줄, 키만)
2. 또는 환경변수 설정: `export GROQ_API_KEY="..."`

### 임베딩 모델 다운로드 지연

첫 실행 시 `BAAI/bge-m3`를 다운로드한다 (~2GB, 네트워크에 따라 수분).
진행률은 콘솔에 출력됨.

### method-1 파일 누락

```
ERROR: method-1/out/stage2_eval_sheet.csv not found
```

method-1를 먼저 실행하거나, 해당 파일을 수동 복사.

---

## 제약 사항

- **평가자 1인, 쿼리 6개** (DESIGN.md §0에 사전 선언)
- **α 고정** (0.5, 평가셋 보고 바꾸지 말 것)
- **블라인드 필수** (arm 비교이므로)
- **결과 분석 금지** (phase2_blind_mapping.csv 미열람)

---

## 참고

- [DESIGN.md](DESIGN.md) — 실험 설계(정본)
- [method-1 보고서](../method-1/README.md) — Phase 1 결과
- `data/ground_truth_labels.csv` — 감사용 정답 라벨
