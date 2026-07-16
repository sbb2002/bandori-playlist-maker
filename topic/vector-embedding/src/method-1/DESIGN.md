# method-1 실험 설계서 — 가사 벡터 검색 (lyrics vector searching)

> **이 문서의 목적**: `notes/01-lyrics_vector-searching.md`(연구자 초안)를 구현 가능한 실험
> 설계로 구체화한 것. **구현자는 이 문서만 보고 코드를 작성할 수 있어야 한다** — 여기 명시된
> 결정(모델명·파라미터·스키마·상수)을 임의로 바꾸지 말고, 막히면 바꾸는 대신 질문할 것.
> 구현 완료 후 저장소 규칙에 따라 이 폴더에 `README.md`(① 방법 소개 ② 실행법)를 작성한다.

## 0. 연구 질문과 판정 기준 (사전 등록)

**RQ1**: 보컬 스템에서 ASR로 추출한 가사를 임베딩해 벡터 검색하면, 한국어 자연어 프롬프트에
"들어보면 맞다" 싶은 곡을 찾아주는가? 가사를 어떤 형태(원문/무드 요약/키워드)로 임베딩하는
것이 가장 잘 맞는가?

**RQ2 (부차)**: 사용자 입력의 구체성(1단계 짧은 요청 vs 4단계 세밀한 감정 서술 —
`notes/01-lyrics_vector-searching.md`의 단계 사다리)이 LLM 확장을 거친 뒤에도 검색 품질
차이를 만드는가? (앱은 짧은 입력을 받아 확장하므로, 확장이 이 격차를 메우는지가 제품 관점의
질문이다.)

**판정 기준 (평가 전에 확정, 사후 변경 금지)** — 최고 성능 (arm × 단계) 조합 기준:

| 판정 | 조건 |
|---|---|
| 채택 후보 | 4개 카테고리 전체 평균 평점 ≥ 3.5 **그리고** 4개 중 3개 이상 카테고리에서 top-5 내 4점 이상 곡 ≥ 2곡 |
| 조건부 재시도 | 전체 평균 2.5 ~ 3.5 → 원인 분해(ASR 품질/임베딩 arm/후보 pool 크기) 후 개선 재실험 |
| 기각 | 전체 평균 < 2.5 |

## 1. 실험 개요

3개 임베딩 조건(arm)을 같은 곡 세트·같은 프롬프트로 비교한다:

| arm | 곡 쪽 텍스트 | 근거 |
|---|---|---|
| `raw` | ASR 가사 원문(경량 정리만) → 다국어 임베딩 | 베이스라인. 일어 가사 ↔ 한국어 프롬프트 교차언어 검색이 되는지 확인 |
| `summary` | LLM이 가사에서 생성한 **한국어 무드 요약문(3문장)** → 임베딩 | 언어·도메인 정규화(topic README 검토 포인트 1-(b)) + 저작권 회피 |
| `keyword` | LLM이 추출한 **한국어 감정/분위기 키워드 8개** → 임베딩 | 초안의 "키워드 위주 산출" 옵션 |

쿼리는 연구자가 `notes/01-lyrics_vector-searching.md`에 작성한 **감정 카테고리 4종(C1 슬픔/
우울, C2 가련함/나아감, C3 힙함/세련됨/시티팝, C4 밝음/아침/위로) × 구체성 단계 사다리** 중
**1단계(L1)와 4단계(L4) 양극단만** 사용한다 = 쿼리 8개 (2·3단계는 평가 부담을 줄이기 위해
이번 실험에서 제외, 후속 실험용으로 notes에 보존). 세 arm 공통으로, 8개 쿼리 전부를 동일하게
LLM으로 감성 서술문(2~3문장)으로 확장한 뒤 임베딩한다(가설 Phase 1의 문장 확장 부분 — L4도
예외 없이 확장해 처리를 균일하게 유지. 에너지 배열은 이번 실험 범위 밖 — 초안 "예상 한계점"
참조).

곡 pool은 `topic/mfcc_analysis`의 30곡 세트(10밴드×3곡)를 재사용한다. 보컬 스템(demucs)이
이미 그쪽 파이프라인 산출물로 존재하기 때문. **pool이 작아 검색 변별력이 낮은 것은 알려진
한계로 기록**하고, 파이프라인 검증이 목적인 1차 실험에서는 감수한다.

### 1b. 카테고리 생성 방식 재설계 (2026-07-17)

2026-07-16 파일럿(14곡 pool, 위 고정 C1~C4 서술문으로 채점)을 검토한 결과 신뢰 불가 판정—
원인은 (a) pool 포화로 14곡 중 12곡이 3~4개 카테고리에 중복 채점됨, (b) 고정 카테고리
서술문이 음향 질감 묘사("재지한 건반", "어쿠스틱 악기" 등)를 포함해 가사 전용 방법론이
원리적으로 만족 불가능한 축을 채점 기준에 섞었고, 카테고리 간 감정 어휘도 중복(고독:
C1·C3, 불안: C2·C4)돼 채점 경계가 흐렸다. 상세 기록: `notes/02-method-01-comment.md`.

이에 따라 **연구자가 손으로 고정한 카테고리 방식을 폐기**하고, 아래 2단계로 전환한다:

- **Stage 1**(이번에 설계·구현): 곡별로 가사를 문장 단위 감성 분석 → 그 곡을 대표하는
  감성을 한국어 한 문장으로 요약(desc) → 그 요약에서 지배적 키워드(main)·2차적 키워드(sub)
  추출. 사람이 desc/키워드가 실제 곡을 정확히 대표하는지 1~5점으로 QC 채점(§6-02b,
  `README.md`의 "프로파일 QC 채점 가이드"). **이 채점은 RQ1(arm 비교)과 직접 연결되지
  않는 별도의 라벨링 검증 단계**다 — 기존처럼 "곡이 사용자 요청과 얼마나 맞는가"를 묻는 게
  아니라 "LLM이 가사에서 뽑아낸 라벨이 정확한가"를 묻는다.
- **Stage 2**(다음 세션, 메커니즘만 설계): Stage 1의 `song_profiles.csv`가 QC를 통과하면,
  그 안의 `keyword_main` 분포에서 자연히 드러나는 클러스터를 쿼리 앵커로 삼아(연구자가 손으로
  쓴 4개 고정 카테고리 대신) 검색 쿼리를 재구성하고, 기존 3-arm 검색·평가(§6-04, §6-05)를
  재실행한다. 한 곡이 여러 키워드-쿼리 top-5에 걸치는 경우는 "전역 최고-cosine 배정" 규칙
  (곡은 자신이 가장 강하게 끌리는 쿼리 하나에만 배정)으로 처리한다. 정확한 키워드 값·쿼리
  문구는 Stage 1 실행 결과가 나와야 정할 수 있으므로 이번 문서에는 아직 확정하지 않는다.

기존 `CATEGORIES`/`PROMPTS`(§5)는 Stage 2가 실행되기 전까지 **미사용(LEGACY)**으로
표시만 하고 삭제하지 않는다 — Stage 2 쿼리 확장 템플릿 설계 시 참고용으로 남겨둔다.

## 2. 전제조건 (구현 전 확인)

1. `topic/mfcc_analysis/stems/htdemucs/<tag>/vocals.wav`가 30곡 모두 존재해야 한다
   (`<tag>`는 `selected_songs.csv`의 `tag` 컬럼, 예: `afterglow__000`).
   **없으면 이 파이프라인에서 demucs를 다시 구현하지 말고**, `topic/mfcc_analysis/README.md`의
   "재생성 순서" 중 `select_songs.py` → `download_missing.py` → `separate_vocals.py`를 먼저
   실행하라고 사용자에게 안내하고 중단한다. (torchaudio/torchcodec 환경 이슈와 우회 러너
   `_demucs_run.py`도 그쪽 README 참조.)
2. 환경변수 `GROQ_API_KEY` 필요 (02 단계). 없으면 02 실행 시점에 명확한 에러로 중단.
3. 패키지: `requirements.txt`로 관리 — `faster-whisper`, `sentence-transformers`, `groq`,
   `pandas`, `numpy`.

## 3. 저작권 규칙 (절대 준수)

- **ASR 가사 원문 텍스트는 git에 커밋하지 않는다.** `work/` 아래에만 두고, 이 폴더의
  `.gitignore`에 `work/`를 반드시 포함한다.
- 커밋 가능한 것: 임베딩 벡터(원문 복원 불가), LLM 파생 무드 요약문·키워드(가사 인용이
  없어야 함 — LLM 프롬프트에서 인용 금지를 명시), 전사 메타데이터(글자수·언어·확신도 등
  통계만).
- LLM 요약/키워드 출력에 가사 문장이 그대로 들어가지 않았는지는 QC 체크포인트(§6)에서
  사람이 확인한다.

## 4. 폴더 구조와 파일 계약

```
src/method-1/
├── DESIGN.md            # 이 문서
├── README.md            # 구현 후 작성 (① 방법 소개 ② 실행법)
├── requirements.txt
├── .gitignore           # work/ 한 줄
├── config.py            # 아래 §5의 상수 전부. 다른 스크립트는 config에서만 상수를 가져온다
├── 01_transcribe.py
├── 02_build_texts.py
├── 03_embed.py
├── 04_search.py
├── 05_analyze.py
├── out/                 # 커밋 대상 산출물 (아래 스키마)
└── work/                # gitignore — 가사 원문 등 (work/transcripts/<tag>.txt)
```

각 스크립트는 **CLI 인자 없이** `python 01_transcribe.py`처럼 실행 가능해야 하고(경로·상수는
전부 `config.py`), **재실행 안전(idempotent)** 해야 한다 — 산출물이 이미 있는 행은 건너뛴다
(특히 01의 ASR과 02의 LLM 호출은 곡 단위로 캐시).

### 산출물 스키마 (`out/`)

| 파일 | 생성 | 컬럼/내용 |
|---|---|---|
| `transcripts_meta.csv` | 01 | `tag, band, song, detected_lang, lang_prob, n_segments, n_chars, avg_logprob_mean` (가사 텍스트 컬럼 금지) |
| `texts_summary.csv` | 02 | `tag, band, song, text` (LLM 한국어 무드 요약문) |
| `texts_keyword.csv` | 02 | `tag, band, song, text` (쉼표로 연결된 키워드 8개) |
| `queries_expanded.csv` | 02 | `prompt_id("C1-L1" 형식), category_id, level, prompt_text, expanded_text` |
| `embeddings.npz` | 03 | key: `raw`, `summary`, `keyword` (각 30×D, `tag` 순서는 `tags` key로 저장), `queries` (8×D, 순서는 `query_ids` key로 저장), 모두 L2 정규화 |
| `results_top5.csv` | 04 | `arm, prompt_id, rank(1-5), tag, band, song, cosine` — **연구자는 평가(§6) 완료 전 이 파일을 열람하지 않는다** |
| `eval_sheet.csv` | 04 | `pair_id, category_id, category_name, category_desc(해당 카테고리 L4 서술문), band, song, url, score, comment` — `score`·`comment`는 빈칸(사람이 기입). **(category, song) 단위** 중복 제거(§6-04 참조), arm·level·유사도 비표시, `SEED`로 셔플 |
| `eval_mapping.csv` | 04 | `pair_id, arm, prompt_id, rank, tag` (eval↔arm·level 역매핑) |
| `analysis_summary.csv` | 05 | (arm×level)×category별 `mean_score, p_at_5, ndcg_at_5` + (arm×level)별 전체 평균 행 |

## 5. 상수 및 파라미터 (`config.py` 에 그대로)

```python
SEED = 42
TOP_K = 5
SONGS_CSV   = "../../../mfcc_analysis/selected_songs.csv"   # method-1 폴더 기준 상대경로
STEMS_DIR   = "../../../mfcc_analysis/stems/htdemucs"       # <tag>/vocals.wav

# ASR
WHISPER_MODEL   = "large-v3"      # 환경변수 WHISPER_MODEL로 오버라이드 가능
WHISPER_COMPUTE = "int8"          # CPU 기준. GPU면 float16으로 오버라이드
# faster-whisper 호출 파라미터(가창 ASR 환각 대책 — 변경 금지):
#   language=None(자동감지), vad_filter=True, temperature=0.0,
#   condition_on_previous_text=False, beam_size=5

# 임베딩
EMBED_MODEL = "BAAI/bge-m3"       # sentence-transformers 로드, 유사도=cosine
                                  # 메모리 부족 시 폴백: intfloat/multilingual-e5-small
                                  # (e5는 곡 텍스트에 "passage: ", 쿼리에 "query: " 접두 필요)

# LLM (Groq)
GROQ_MODEL = "llama-3.3-70b-versatile"   # 환경변수 GROQ_MODEL로 오버라이드
                                          # (앱 기본값 llama-3.1-8b-instant보다 상위 모델 —
                                          #  연구 단계는 지연보다 요약 품질 우선)
GROQ_TEMPERATURE = 0.0

# 평가 쿼리: 감정 카테고리 4종 × 구체성 2단계 = 8개
# LEGACY (2026-07-17 — §1b 참조): Stage 2가 실행되기 전까지 미사용. 카테고리는
# song_profiles.csv의 keyword_main/keyword_sub에서 동적으로 나온다. Stage 2 쿼리
# 확장 템플릿 설계 시 참고용으로만 존치.
CATEGORIES = {
    "C1": "슬픔/우울",
    "C2": "가련함/나아감",
    "C3": "힙함/세련됨/시티팝",
    "C4": "밝음/아침/위로",
}
PROMPTS = {
    "C1-L1": "우울하고 슬픈 노래 틀어줘.",
    "C1-L4": "짙은 밤하늘 아래 홀로 남겨진 듯한 고독감이 밀려오지만, 애써 담담하게 슬픔을 받아들이며 조용히 내면을 위로하는 애절하고 서정적인 정서.",
    "C2-L1": "희망찬데 슬픈 노래.",
    "C2-L4": "금방이라도 부서질 것처럼 연약하고 서글픈 보컬의 목소리 뒤로, 세차게 몰아치는 드럼과 기타 사운드가 질주하며 불안 속에서도 끝내 딛고 일어나 나아가고자 하는 아련하고 가련한 의지.",
    "C3-L1": "힙하고 세련된 노래.",
    "C3-L4": "지나치게 무겁지 않은 미디엄 템포 위에 재지(Jazzy)한 건반과 찰진 베이스 리듬이 얹혀, 도회적인 고독과 낭만이 교차하는 감각적이고 스타일리시한 무드.",
    "C4-L1": "아침에 듣기 좋은 밝은 노래.",
    "C4-L4": "이른 아침의 맑은 공기와 부드러운 햇살이 스며들 듯, 어쿠스틱한 악기들이 만드는 포근한 공간감 속에서 불안을 걷어내고 긍정적인 온기를 불어넣는 나른하면서도 화사한 순간.",
}

# Stage 1 (§1b, §6-02b): 곡별 가사 프로파일링 프롬프트. PROMPTS/CATEGORIES와 달리
# 검색용 텍스트가 아니라 사람이 QC 채점하는 곡 라벨(desc/keyword_main/keyword_sub)을
# 생성한다 — 아래 템플릿 (e) 참조.
PROFILE_PROMPT = """다음은 어느 노래의 가사다(일본어 또는 영어), 여러 문장/구절로 이루어져 있다.

1. 가사를 문장(또는 절) 단위로 끊어 각 문장에서 느껴지는 감정을 파악하라(이 분석 과정
   자체는 출력하지 않는다).
2. 문장별 감정을 종합해, 이 곡 전체를 지배하는 감정과 서사를 한국어 한 문장으로 요약하라.
3. 그 요약 문장에서 가장 중심이 되는 감정/분위기 키워드 1개(지배적 키워드)와, 그다음으로
   두드러지는 키워드 1개(2차적 키워드)를 뽑아라.

규칙: 가사 원문의 문장이나 구절을 그대로 인용·번역하지 말 것. 곡 제목·아티스트명·고유명사를
쓰지 말 것. 키워드는 명사 또는 형용사 단어 하나씩만(구·문장 금지). 사운드·템포·악기에 대한
묘사는 쓰지 말 것(감정과 상황만).

출력 형식(반드시 이 3줄 형식으로만 출력):
DESC: <한국어 한 문장>
MAIN: <키워드 1개>
SUB: <키워드 1개>

가사:
{lyrics}"""
```

### LLM 프롬프트 템플릿 (그대로 사용, `{lyrics}`/`{prompt}` 치환)

**(a) 무드 요약 (`texts_summary`)**
```
다음은 어느 노래의 가사다(일본어 또는 영어).
이 노래의 정서·분위기·에너지를 한국어 3문장으로 서술하라.
규칙: 가사 원문의 문장이나 구절을 인용·번역해 옮기지 말 것. 곡 제목이나 고유명사를 쓰지 말 것.
감정(예: 쓸쓸함, 벅참), 분위기(예: 몽환적, 공격적), 에너지(예: 잔잔함, 질주감) 위주로만 서술할 것.

가사:
{lyrics}
```

**(b) 키워드 추출 (`texts_keyword`)**
```
다음은 어느 노래의 가사다(일본어 또는 영어).
이 노래의 감정·분위기를 나타내는 한국어 키워드 8개를 골라라.
규칙: 명사 또는 형용사만. 가사 단어를 그대로 옮기지 말 것. 쉼표로 구분해 한 줄로만 출력할 것.

가사:
{lyrics}
```

**(c) 쿼리 확장 (`queries_expanded`)**
```
사용자가 플레이리스트를 요청했다: "{prompt}"
이 요청이 원하는 노래의 정서·분위기·에너지를 한국어 2~3문장으로 더 풍부하게 서술하라.
곡 제목·아티스트·장르 명칭은 쓰지 말고, 감정과 분위기 서술만 출력할 것.
```

**(e) 곡 프로파일링 (`song_profiles`, Stage 1 — §1b) — 원문은 `PROFILE_PROMPT`(§5) 참조**

(a)/(b)와 목적이 다르다: (a)/(b)는 arm이 실제 임베딩하는 검색용 텍스트고, (e)는 검색과
무관한 곡 자체의 라벨(QC 채점 대상)이다. 이전 라운드에서 검토했던 "채점 보조용 독립 요약"
아이디어는 이 (e)로 흡수됨 — desc/키워드 자체가 곧 채점 대상이자 보조자료가 되므로 별도
프롬프트가 더 필요 없다.

## 6. 파이프라인 단계별 명세

### 01_transcribe.py — ASR
- 입력: `SONGS_CSV`의 30행, 각 `STEMS_DIR/<tag>/vocals.wav`.
- faster-whisper로 전사(§5 파라미터). 세그먼트 텍스트를 순서대로 모은다.
- **후처리(결정적)**: 각 세그먼트 텍스트를 strip → 연속으로 동일한 세그먼트는 1개로 축약
  (환각 루프 대책) → 개행으로 join.
- 출력: `work/transcripts/<tag>.txt`(원문, 커밋 금지) + `out/transcripts_meta.csv`.
- 캐시: `<tag>.txt`가 이미 있으면 해당 곡 스킵.
- **QC 체크포인트 (사람)**: 완료 후 연구자가 3곡 이상 골라 원문을 실제 청취와 대조해 ASR
  품질을 확인하고 나서 02로 진행한다. 스크립트는 마지막에 이 안내문을 출력할 것.

### 02_build_texts.py — 텍스트 변형 3종 + 쿼리 확장 (Groq)
- `raw` arm 텍스트는 `work/transcripts/<tag>.txt`를 그대로 사용(추가 파일 생성 없음).
- 곡마다 템플릿 (a)·(b)로 Groq 호출 → `out/texts_summary.csv`, `out/texts_keyword.csv`.
- 쿼리 8종(`PROMPTS`)에 템플릿 (c) 적용 → `out/queries_expanded.csv`.
- 캐시: 출력 CSV에 이미 있는 `tag`/`prompt_id`는 재호출하지 않는다(행 단위 append).
- **QC 체크포인트 (사람)**: 요약·키워드에 가사 원문 인용이 섞이지 않았는지 표본 확인(§3).

### 02b_profile_songs.py — 곡별 가사 프로파일링 + QC 평가지 생성 (Stage 1, §1b)

기존 00~05 파이프라인과 독립적으로 동작한다 — 임베딩·검색과 무관하다.

- 입력: `SAMPLE_TAGS`의 각 태그 → `work/transcripts/<tag>.txt`(01단계 산출물, 이미 존재).
- 곡마다 템플릿 (e)(`PROFILE_PROMPT`)로 Groq 호출 → 응답에서 `DESC:`/`MAIN:`/`SUB:` 3줄을
  정규식으로 파싱. 형식이 어긋나면 `retry_with_backoff`로 재시도, 그래도 실패하면 해당 곡을
  실패 목록에 남기고 사람에게 알린 뒤 중단(다른 단계와 동일한 에러 처리 원칙).
- 캐시: 이미 `song_profiles.csv`에 있는 `tag`는 재호출하지 않는다(행 단위, 02_build_texts.py
  와 동일 패턴).
- 출력 ①: `out/song_profiles.csv` — `tag, band, song, desc, keyword_main, keyword_sub`.
- 출력 ②: `out/profile_qc_sheet.csv` — 채점용 시트, 컬럼: `pair_id, tag, band, song, url,
  desc, keyword_main, keyword_sub, score, comment`. 곡당 정확히 1행 — dedup 로직 불필요
  (기존 04_search.py의 `(category_id, tag)` 문제가 애초에 발생하지 않는 구조). `pair_id`는
  04_search.py와 같은 방식으로 `random.Random(SEED).shuffle` 후 `p001`부터 부여.
- **QC 체크포인트 (사람)**: `desc`에 가사 원문이 그대로 인용되지 않았는지 표본 확인(§3).
  블라인드 요구사항(다른 산출물 열람 금지)은 **해당 없음** — arm 비교가 아니므로.
- 채점 rubric은 `README.md`의 "프로파일 QC 채점 가이드" 절이 정본.

### 03_embed.py — 임베딩
- `EMBED_MODEL` 로드. 곡 텍스트 3종(raw는 work/에서, summary·keyword는 out/ CSV에서)과
  `expanded_text` 5개를 인코딩, L2 정규화 후 `out/embeddings.npz` 저장(§4 스키마).
- 곡 순서는 `SONGS_CSV` 행 순서로 통일하고 `tags` 배열을 함께 저장.

### 04_search.py — 검색 + 평가지 생성
- 각 arm × 쿼리 8종에 대해 cosine(내적, 정규화 완료) top-5 → `out/results_top5.csv`
  (3 arm × 8 쿼리 × 5 = 120행).
- **평가 pair는 (category_id, tag) 단위로 중복 제거**한다 — 같은 카테고리의 L1/L4 쿼리와
  세 arm이 뽑은 곡은 한 번만 평가한다. 근거: 평가가 측정하는 것은 "곡 ↔ 카테고리 의도"의
  일치이고, L1은 L4가 서술한 의도의 축약형이므로 기준문은 카테고리당 하나(L4 서술문 =
  `category_desc`)로 통일한다. 평가 부담이 절반 이하로 줄어든다(카테고리당 최대 30곡,
  실질 10~15곡 예상 → 총 40~60개 평가). **단, 이 기준문 통일이 L1 쿼리에 불리할 수 있음**
  (L1이 요구하지 않은 뉘앙스까지 기준에 포함)은 한계(§8)에 기록한다.
- pair 목록을 `random.Random(SEED).shuffle` → `pair_id`를 `p001`부터 부여 →
  `out/eval_sheet.csv`(블라인드) + `out/eval_mapping.csv`.
- `url`은 `SONGS_CSV`의 `url` 컬럼에서 join.
- 실행 후 안내문 출력: "eval_sheet.csv의 score(1~5)를 채우기 전에는 results_top5.csv를
  열람하지 말 것".
- **채점 앵커(1~5 기준)와 채점 규칙은 `README.md`의 "평가 가이드 (채점 기준)" 절이 정본** —
  평가 시작 전(2026-07-16) 확정했으며 채점 도중 변경 금지.

### 05_analyze.py — 집계
- `eval_sheet.csv`의 score가 전부 채워졌는지 검증(빈칸 있으면 목록 출력 후 중단).
- `eval_mapping.csv`로 (arm, level)에 점수를 되붙여 (arm×level)×category별:
  - `mean_score` = top-5 평점 평균
  - `p_at_5` = top-5 중 score≥4 곡 수 / 5
  - `ndcg_at_5` = DCG(gain=score-1, log2 할인, rank순) / IDCG(그 카테고리에서 **평가된 전체
    pair** 중 상위 5개 기준)
- (arm×level)별 전체 평균 행 포함 `out/analysis_summary.csv` 저장 + stdout에 출력할 것:
  ① §0 판정 기준에 따른 판정문(최고 (arm×level) 조합 기준), ② RQ2용 부차 분석 — arm별
  L1 vs L4 평균 격차 표(확장이 입력 구체성 격차를 메우는지), ③ 마크다운 요약 표.
- 최종 보고서(`report/01-lyrics_vector-searching.md`)는 이 결과를 바탕으로 연구자/상위
  세션이 작성한다 — 이 스크립트의 범위 밖.

## 7. 서브 로컬 샘플 실행 노트 (2026-07-16 — 이번 실행에서 §2·§5를 아래처럼 오버라이드)

이번 실행은 **서브 로컬 기기**(GPU 없음, CPU 전용)에서 수행하며, 로컬에 30곡 중 21곡(7밴드×3)의
오디오만 있고 demucs 스템은 전무하다. 전체 처리 시 수 시간이 걸리므로 **총 90분 이내** 완료를
위해 다음과 같이 축소·조정한다:

- **곡 pool = 14곡** (로컬 보유 7밴드 × idx 순 2곡). `config.py`에 명시 고정:
  ```python
  SAMPLE_TAGS = [
      "afterglow__000", "afterglow__001", "ave_mujica__072", "ave_mujica__073",
      "hello_happy_world__106", "hello_happy_world__107", "morfonica__180", "morfonica__181",
      "mugendai_mutype__237", "mugendai_mutype__238", "mygo__260", "mygo__261",
      "pastel_palettes__301", "pastel_palettes__302",
  ]
  AUDIO_DIR = r"C:\Users\user\Documents\myprojects\bandori-song-sorter\src\content\cluster\audio_full"  # <tag>.wav
  STEMS_DIR = "work/stems"   # §5의 mfcc_analysis 경로 대신 — 이 폴더 안에서 자체 생성
  WHISPER_MODEL = "medium"   # large-v3 대신(시간 예산). 나머지 ASR 파라미터는 §5 그대로
  ```
- **`00_prepare_stems.py` 추가**: `SAMPLE_TAGS` 중 `STEMS_DIR/<tag>/vocals.wav`가 없는 곡만
  `AUDIO_DIR/<tag>.wav`에서 demucs two-stems 보컬 분리(§2의 "demucs 재구현 금지"의 예외 —
  단, 분리 로직을 새로 짜지 말고 `topic/mfcc_analysis/_demucs_run.py`의 몽키패치 러너를
  그대로 복사/재사용할 것. torchaudio/torchcodec 이슈 대비). 출력 구조는
  `work/stems/<tag>/vocals.wav`로 demucs 기본 출력에서 정리.
- 01~05는 `SAMPLE_TAGS` 14곡 기준으로 동작(=`SONGS_CSV`를 읽되 `SAMPLE_TAGS`로 필터).
- `GROQ_API_KEY`는 환경변수 우선, 없으면 `work/groq.key` 파일(1줄, gitignore 영역)에서 읽는다.
- **판정 유보**: pool이 14곡으로 줄어 §0 판정 기준은 참고치로만 본다 — 이번 실행의 1차 목적은
  파이프라인 검증과 예비 판독이고, 정식 판정은 풀 30곡(또는 660곡 확장) 실행에서 한다.

## 8. 알려진 한계 (보고서에 그대로 기록할 것)

- 음향 통계값 미사용 — 가사 단독 효과만 측정(초안 "예상 한계점" 그대로).
- pool 30곡 → top-5 변별력 제한. 후속으로 660곡 전체 확장 시 ASR·임베딩은 오프라인
  사전계산 필요.
- 평가자 1인(연구자 본인) 설문 — 블라인드 평가지로 arm 편향은 차단하지만 개인 취향 편향은
  남는다.
- ASR 오류(가창 WER·환각)는 QC로 표본 확인만 하고 정량 측정하지 않는다.
- 평가 기준문을 카테고리당 L4 서술문 하나로 통일(§6-04) — L1 쿼리가 요구하지 않은 뉘앙스까지
  기준에 포함되어 L1 성적이 체계적으로 불리해질 수 있다. RQ2의 L1 vs L4 격차 해석 시 이
  편향을 감안할 것.
- 구체성 사다리의 2·3단계 프롬프트는 미사용(notes에 보존) — 단계별 세밀한 용량-반응 관계는
  후속 실험 몫.
- 고정 카테고리 서술문의 confound(음향 질감 언어, 카테고리 간 어휘 중복)로 2026-07-16
  파일럿(v1, 14곡 pool)이 신뢰 불가 판정됨 → §1b의 Stage 1(가사 유래 desc/키워드)로 전환.
  v1 산출물(`out/eval_sheet.csv`, 42행)은 삭제하지 않고 파일럿 기록으로만 보존.
