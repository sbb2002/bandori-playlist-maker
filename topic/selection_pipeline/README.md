# selection_pipeline: 선곡 파이프라인 3-way 비교 실험

> **🔒 종결(2026-07-18)**: v1·v2는 프로덕션을 단순 재현한 버전으로 비교했다는 게 드러나(밝기
> tie-break·Stage B 시퀀싱 생략), v3에서 **실제 프로덕션 코드(`build_setlist()`)를 그대로
> 재사용**해 Method1(현행) vs Method2(+Stage C)로 재검증 — 역시 유의한 차이 없음(오히려 Method1
> 근소 우위). 세 번의 독립 시도 모두 가사 후보추림 도입 근거를 못 냈다 →
> **주제 최종 종결, `selection.py`는 현행 유지 확정**. 최종 결론은
> `report/03-selection_pipeline_v3_method_comparison.md`, 이전 라운드는 `report/01-*.md`·
> `report/02-*.md` + `DESIGN.md`(v1)/`DESIGN_v2.md`(v2)/`DESIGN_v3.md`(v3)에 보존. 아래 실행
> 가이드는 v1 재현/참고용으로 남겨둔다.

선곡 로직의 세 가지 구조를 비교하는 블라인드 평가 실험.

- **Arm 1**: 절대 강도(intensity) 매칭만 사용 — 현재 프로덕션 방식
- **Arm 2**: 가사 후보추림 + 절대 강도
- **Arm 3**: 가사 후보추림 + 밴드 상대 백분위(band_pct) — v1에서 구조 기각, v2 재검증 대상 아님

**설계 문서**: `DESIGN.md`(v1, 3-way) · `DESIGN_v2.md`(v2, 84쿼리 재검증)

---

## 사전 요구사항

### 의존성
- **Python 3.10+** (conda env `warmth`)
- 의존성 설치 위치:
  - `sentence-transformers` (for BAAI/bge-m3 embedding)
  - `pandas`, `numpy`
  - `groq` (for Groq API client)

### Groq API 키
`work/groq.key` 파일에 저장하거나 `GROQ_API_KEY` 환경변수로 설정.
```bash
# Option 1: File
mkdir -p topic/selection_pipeline/work
echo "your-api-key-here" > topic/selection_pipeline/work/groq.key

# Option 2: Environment
export GROQ_API_KEY="your-api-key-here"
```

### 선행 단계 완료
- `topic/vector-embedding/src/method-1/` ✓ Stage 1 완료
  - `full_catalog_songs.csv` (661곡)
  - `out/song_profiles.csv` (가사 기반 프로파일)
- `topic/vector-embedding/src/method-2/` ✓ Stage 2 완료
  - `out/song_acoustics.csv` (음향 지표)

---

## 실행 순서 (DESIGN.md §6)

### Step 1: Query targets 추출
LLM으로 각 쿼리에서 강도 목표(intensity_target)와 밴드 필터(band_filter)를 추출.

```bash
cd C:/Users/User/Documents/pyworks/bandori-playlist-maker
$env:PYTHONIOENCODING = "utf-8"
C:/Users/User/miniconda3/envs/warmth/python.exe topic/selection_pipeline/01_query_targets.py
```

**산출물**: `topic/selection_pipeline/out/query_targets.csv`

**검토 체크포인트**: 추출된 intensity_target과 band_filter가 쿼리와 논리적으로 맞는지 확인.

---

### Step 2: 밴드별 강도 백분위 계산
각 곡의 강도 백분위를 자신이 속한 밴드 내에서 계산.
(전체 661곡 내 백분위가 아니라, 같은 밴드 곡들 내에서의 백분위)

```bash
$env:PYTHONIOENCODING = "utf-8"
C:/Users/User/miniconda3/envs/warmth/python.exe topic/selection_pipeline/02_band_percentiles.py
```

**산출물**: `topic/selection_pipeline/out/song_band_percentiles.csv`

**검토 체크포인트**: 
- `report/05-energy_distribution_by_band.md`의 "밴드별 분포" 표와 중앙값 비교
- 밴드별 곡 수, 강도 분포 확인

---

### Step 3: 가사 후보추림 (arm 2·3 공통)
각 쿼리에 대해 가사 임베딩으로 상위 20% 곡을 선별.

- LLM으로 쿼리 확장 (2~3문장 묘사로 상세화)
- `BAAI/bge-m3` 임베딩으로 코사인 유사도 계산
- 상위 N곡 추출 (N = max(15, ceil(0.20 * eligible_pool_size)))

```bash
$env:PYTHONIOENCODING = "utf-8"
C:/Users/User/miniconda3/envs/warmth/python.exe topic/selection_pipeline/03_lyric_candidates.py
```

**산출물**: 
- `topic/selection_pipeline/out/queries_expanded.csv` (LLM 확장 결과)
- `topic/selection_pipeline/out/query_lyric_candidates.csv` (각 쿼리별 top-N)

**검토 체크포인트**: 상위 후보들이 직관적으로 합리적인지 확인 (선택사항).

---

### Step 4: 세 arm 실행
각 쿼리에 대해 arm 1/2/3 각각 top-3을 추출.

```bash
$env:PYTHONIOENCODING = "utf-8"
C:/Users/User/miniconda3/envs/warmth/python.exe topic/selection_pipeline/04_run_arms.py
```

**산출물**: `topic/selection_pipeline/out/method3_arm_results.csv`
- Columns: query_id, arm, rank, tag, band, song, intensity, band_pct, lyric_cosine
- 총 3 arms × 8 queries × 최대 3 ranks = 최대 72행

---

### Step 5: 블라인드 평가 시트 생성
세 arm의 top-3 합집합을 생성, 셔플하고, 정체 노출 컬럼 제거.

```bash
$env:PYTHONIOENCODING = "utf-8"
C:/Users/User/miniconda3/envs/warmth/python.exe topic/selection_pipeline/05_build_blind_sheet.py
```

**산출물**:
1. **`topic/selection_pipeline/out/method3_blind_sheet.csv`** (평가용)
   - Columns: eval_id, query_id, prompt_text, band, song, url, score (empty), comment (empty)
   - 1~5 Likert scale 점수를 `score` 컬럼에 입력할 것
   - 스크립트가 콘솔에 **총 고유 쌍 수를 출력** → 이 수를 확인한 후 청취 착수 결정

2. **`topic/selection_pipeline/out/method3_blind_mapping.csv`** (언블라인드용, 평가 전까지 미열기)
   - Columns: eval_id, query_id, tag, arms, intensity, band_pct, intensity_target
   - 채점 완료 후 분석 단계에서만 열 것

---

## 평가 (수동)

### Step 5 후 검토
콘솔에 출력된 "실제 고유 쌍 수"를 확인.
```
Actual unique pairs: XX
```
이 수가 예상 범위(~40~60곡 추정) 내에 있는지 확인 후 청취 착수.

### 청취 및 점수 입력
1. `method3_blind_sheet.csv` 열기
2. 각 행에 대해:
   - 곡 재생 (YouTube URL 클릭 또는 로컬 파일 재생)
   - 쿼리와의 일치도를 **1~5 Likert scale**로 평가:
     - **1**: 전혀 일치하지 않는다
     - **2**: 거의 일치하지 않는다
     - **3**: 중간 정도 일치한다
     - **4**: 상당히 일치한다
     - **5**: 매우 잘 일치한다
   - `score` 컬럼에 숫자 입력
   - 필요시 `comment` 컬럼에 메모 추가

### 언블라인드 및 분석
점수 입력 완료 후:
```python
# Python에서 언블라인드
df_blind = pd.read_csv("topic/selection_pipeline/out/method3_blind_sheet.csv")
df_mapping = pd.read_csv("topic/selection_pipeline/out/method3_blind_mapping.csv")

# eval_id로 조인하면 어느 arm이었는지 확인 가능
result = df_blind.merge(df_mapping, on="eval_id")
```

DESIGN.md §0의 판정표 적용하여 최종 결론 도출.

---

## 공통 규칙

### 환경변수
```bash
# PowerShell에서
$env:PYTHONIOENCODING = "utf-8"  # 필수 (한글 출력용)
$env:GROQ_API_KEY = "..."         # 선택 (또는 work/groq.key 파일)
```

### 직접 Python 호출 (conda run 금지)
conda run은 Windows cp949 인코딩 이슈로 한글이 깨짐.
```bash
# ✅ Correct
C:/Users/User/miniconda3/envs/warmth/python.exe script.py

# ❌ Wrong
conda run -n warmth python script.py
```

### Idempotent (재개 가능)
모든 스크립트는 산출물이 이미 있으면 해당 항목을 건너뜀.
```
01: out/query_targets.csv 있으면 skip
02: 항상 재계산 (의존성 명확)
03: out/query_lyric_candidates.csv 있으면 skip (LLM 호출 절감)
04: out/method3_arm_results.csv 있으면 skip
05: 항상 재계산 (셔플 seed 고정)
```

### 진행률 JSON
01, 03번 스크립트(LLM 호출)는 `out/<step>_progress.json`에 진행 상황 기록.
```json
{
  "steps": {
    "extract_targets": {
      "status": "in_progress",
      "n_done": 3,
      "n_total": 8
    }
  },
  "updated_at": "2026-07-18T..."
}
```
실행 중 진행률 확인:
```bash
# PowerShell
Get-Content -Raw "topic/selection_pipeline/out/01_query_targets_progress.json" | ConvertFrom-Json
```

---

## 트러블슈팅

### Groq API 키 오류
```
ERROR: GROQ_API_KEY not found. Set env GROQ_API_KEY or create work/groq.key
```
→ `work/groq.key` 파일 생성하거나 환경변수 `GROQ_API_KEY` 설정.

### Embedding 모델 다운로드
첫 실행 시 `BAAI/bge-m3` 모델을 자동 다운로드 (수 GB, 시간 소요).
이후 캐시됨.

### 메모리 부족
Song 임베딩(661곡)은 메모리 약 1~2GB 소비.
장비에 메모리가 부족하면 배치 크기 줄이기 (코드 수정 필요).

---

## 파일 구조

```
topic/selection_pipeline/
├── DESIGN.md                          # 설계 문서 (필독)
├── README.md                          # 이 파일
├── config.py                          # 경로·모델·쿼리 설정
├── 01_query_targets.py                # LLM 추출
├── 02_band_percentiles.py             # 밴드 백분위 계산
├── 03_lyric_candidates.py             # 가사 임베딩 검색
├── 04_run_arms.py                     # 3 arm 실행
├── 05_build_blind_sheet.py            # 블라인드 시트 생성
├── out/                               # 산출물 디렉토리
│   ├── query_targets.csv
│   ├── song_band_percentiles.csv
│   ├── queries_expanded.csv
│   ├── query_lyric_candidates.csv
│   ├── method3_arm_results.csv
│   ├── method3_blind_sheet.csv        # 평가 시트 (점수 입력 대상)
│   ├── method3_blind_mapping.csv      # 언블라인드용 (평가 후)
│   └── *_progress.json                # LLM 단계의 진행률
└── work/                              # gitignore (API 키 등)
    └── groq.key                       # Groq API 키 (미포함)
```

---

## 참고 문서

- `DESIGN.md` — 전체 설계 (구현의 원본)
- `topic/vector-embedding/report/05-energy_distribution_by_band.md` — 밴드별 강도 분포 (band_pct 맥락)
- `topic/vector-embedding/src/method-1/06_stage2_search.py` — 가사 임베딩 검색 (재사용 참고)
- `topic/vector-embedding/src/method-2/DESIGN.md` — 음향 지표 정의 (intensity 축)
