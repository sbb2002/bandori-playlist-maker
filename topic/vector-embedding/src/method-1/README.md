# Method 1: Lyrics Vector Search

## Overview

This experiment evaluates whether vector search on **vocal stems' ASR-extracted lyrics** can find songs that match natural-language mood requests. We compare three text representations (embedding arms):

1. **raw**: ASR transcript (original lyrics)
2. **summary**: LLM-generated 3-sentence mood summary (in Korean)
3. **keyword**: LLM-extracted 8 emotional/atmospheric keywords (in Korean)

Each arm is tested against 8 user prompts (4 mood categories × 2 levels of specificity: L1 short vs. L4 detailed), using cosine similarity search on BGE-M3 embeddings.

**Goal**: Identify whether lyrics-based vector search is a viable mechanism for the playlist-generation app, and which text representation (raw/summary/keyword) works best.

## Quick Start

### Prerequisites

1. **Python environment**: Python 3.8+ with packages listed in `requirements.txt`
   ```bash
   pip install -r requirements.txt
   ```

2. **Groq API key**: Required for steps 02 onwards
   - Set environment variable: `export GROQ_API_KEY=your-key`
   - OR create `work/groq.key` file with your key (one line, no newline)

3. **Vocal stems**: Either:
   - Use the automated preparation step (00_prepare_stems.py) if you have `AUDIO_DIR` songs
   - OR run `topic/mfcc_analysis/README.md` steps to generate stems manually

### Pipeline Steps

Run in order. **Each step is idempotent** — re-running skips already-processed files.

#### 00_prepare_stems.py — Vocal Separation (optional)

Extracts vocal stems from audio files using demucs (two-stems mode).

```bash
# Prepare all songs (or just first 1 for smoke test)
python 00_prepare_stems.py [--limit N]
```

**Output**: `work/stems/<tag>/vocals.wav` for each song

---

#### 01_transcribe.py — ASR Transcription

Transcribes vocals using faster-whisper (medium model, CPU-optimized int8).

```bash
python 01_transcribe.py
```

**Outputs**:
- `work/transcripts/<tag>.txt` — ASR lyrics (gitignored)
- `out/transcripts_meta.csv` — metadata (language, n_chars, confidence, etc.)

**QC Checkpoint**: Before proceeding to step 02, manually verify 3+ transcripts:
1. Listen to the audio clip
2. Read the transcript
3. Check for hallucinations (repeated words/phrases)

If acceptable, continue; otherwise, investigate ASR parameter tuning.

---

#### 02_build_texts.py — LLM Text Generation

Generates mood summaries and keywords using Groq LLM, and expands all user prompts.

```bash
GROQ_API_KEY=your-key python 02_build_texts.py
# or with key file:
python 02_build_texts.py
```

**Outputs**:
- `out/texts_summary.csv` — 3-sentence Korean mood summaries
- `out/texts_keyword.csv` — comma-separated keywords (8 per song)
- `out/queries_expanded.csv` — LLM-expanded user prompts (2–3 sentences each)

**QC Checkpoint**: Verify that summaries/keywords don't contain verbatim lyrics quotes:
1. Spot-check 3+ entries in `texts_summary.csv`
2. Spot-check 3+ entries in `texts_keyword.csv`
3. If quotes found, file an issue (LLM prompt refinement)

---

#### 03_embed.py — Embedding

Encodes all songs and queries using BGE-M3 (multilingual) with L2 normalization.

```bash
python 03_embed.py
```

**Output**: `out/embeddings.npz`
- Keys: `raw`, `summary`, `keyword` (song embeddings, each 14×D)
- Keys: `queries`, `query_ids` (query embeddings, 8×D, with IDs)
- Key: `tags` (song order for reference)

---

#### 04_search.py — Cosine Search & Evaluation Sheet

Performs top-5 cosine similarity search for each arm and query, then generates blind evaluation forms.

```bash
python 04_search.py
```

**Outputs**:
- `out/results_top5.csv` — raw search results (for reference only, don't open yet)
- `out/eval_sheet.csv` — **blind evaluation form** (to be scored by human)
- `out/eval_mapping.csv` — metadata for re-linking scores to arms/levels after evaluation

**Important**: Do NOT open `results_top5.csv` until evaluation is complete (prevents bias).

**Deduplication**: Pairs are unique by `(category_id, song_tag)`. This means:
- If the same song appears in top-5 for multiple queries in the same category, it's scored once
- Scoring is based on the category description (L4 prompt for that category)

---

#### Evaluation Step (Human Scoring)

1. Open `out/eval_sheet.csv` in a spreadsheet editor
2. For each row:
   - Listen to the song (via YouTube URL in `url` column)
   - Rate how well it matches the category mood (1–5 scale)
   - Optionally add comments
3. Fill in the `score` and `comment` columns
4. Save and close

**Scoring scale**: 아래 한국어 "평가 가이드 (채점 기준)" 절이 정본이다 — 반드시 그 앵커대로 채점할 것.

---

## 평가 가이드 (채점 기준) — 2026-07-16 평가 시작 전 확정

어느 로컬·어느 세션에서 채점해도 동일한 기준이 되도록 앵커를 고정한다.
**변경 금지** — 채점 도중 기준을 바꾸면 이미 매긴 점수와 비교 불능이 된다.

### 무엇과 비교해 채점하나

각 행의 `category_desc`(그 감정 카테고리의 4단계 상세 서술문)가 **기준문**이다. 곡을 듣고
기준문과의 일치도를 세 축으로 나눠 본다:

1. **정서(emotion)** — 기준문이 말하는 감정 종류(슬픔·연약한 의지·도회적 고독·아침의 온기 등)가 느껴지는가
2. **분위기(texture)** — 사운드 질감·무드(서정적/질주하는 밴드사운드/재지한 그루브/어쿠스틱 포근함)가 부합하는가
3. **에너지(energy)** — 템포·강도(잔잔함↔몰아침)가 기준문의 수준과 맞는가

### 점수 앵커

| 점수 | 기준 |
|---|---|
| 5 | 세 축 모두 부합 — "이 서술문을 위해 고른 곡" 수준 |
| 4 | 두 축 이상 부합하고 나머지 한 축도 크게 어긋나지 않음 |
| 3 | 방향은 맞음(한 축 정도 부합)이지만 나머지가 어긋남 — "틀리진 않은데 추천이라기엔 애매" |
| 2 | 대체로 안 맞음 — 스치는 요소가 하나 정도 |
| 1 | 무관하거나 정반대 인상 |

### 채점 규칙

- **곡 전체 인상**으로 판단한다 — 최소한 절(verse)과 후렴(chorus)을 포함해 듣는다. 도입부
  몇 초만 듣고 매기지 않는다.
- 같은 곡이 **다른 카테고리 행**으로 또 나오면 각각 독립적으로 채점한다 (한 곡이 C1에 4점,
  C4에 1점일 수 있다 — 정상).
- 판단 재료는 **들리는 인상(사운드+보컬의 정서)이 기본**이다. 일본어 가사를 알아듣거나 아는
  곡이라 가사 내용을 알면 반영해도 된다(실제 앱 사용자도 그렇게 듣는다). 단, 가사를 찾아보는
  등의 추가 조사는 하지 않는다.
- `comment`는 선택이지만 **3점 이하는 이유 한 줄 권장** (예: "에너지는 맞는데 정서가 밝음") —
  나중에 오류 분석 재료가 된다.
- **채점자는 연구자 1인으로 고정** — 기기가 바뀌어도 같은 사람이 채점한다(평가자 간 편차 배제).
  중간에 끊고 나중에(다른 기기에서) 이어 채점해도 된다.
- **블라인드 유지**: 채점을 전부 마치기 전에는 `results_top5.csv`·`eval_mapping.csv`·
  `analysis_summary.csv`를 열지 않는다. 어떤 arm이 그 곡을 뽑았는지 모르는 상태가 유지돼야 한다.

### 채점 후 남은 절차 (어느 세션이든 이어받기 가능)

1. `score`가 전부 채워진 `eval_sheet.csv`를 research 브랜치에 커밋·푸시.
2. `python 05_analyze.py` 실행 → `out/analysis_summary.csv` + stdout 판정문(§0 기준은 14곡
   샘플이므로 **참고치**).
3. Claude 세션에 결과 해석을 요청 → `topic/vector-embedding/report/01-lyrics_vector-searching.md`
   해석 레포트 작성(DESIGN §0 판정 + RQ2 L1/L4 격차 + 한계 §8 명시). 이해를 돕는 플롯은
   Haiku 서브에이전트에 위임해 `topic/vector-embedding/fig/`에 생성(토큰 절감 방침).
4. 레포트까지 커밋·푸시.

### 진행 상태 (2026-07-16, 서브 로컬)

- 완료: 00(스템 14곡)~04(평가지 생성) 전부 + Groq/ASR QC 통과. 산출물은 `out/`에 커밋됨.
- 대기: **eval_sheet.csv 42행 채점** (위 기준) → 이후 절차 3단계.
- 서브 로컬에만 있는 것(`work/`, 미커밋): 전사 원문 14곡·보컬 스템·groq.key — 채점에는 불필요.
  다른 기기에서 02 재실행 시 groq.key만 재배치.

---

#### 05_analyze.py — Metrics & Judgment

Validates scoring, computes evaluation metrics, and outputs final judgment.

```bash
python 05_analyze.py
```

**Outputs**:
- `out/analysis_summary.csv` — metrics table (mean_score, p@5, ndcg@5 by arm×level×category)
- **stdout**: judgment (Adopt/Conditional Retry/Reject), RQ2 analysis (expansion gap), markdown summary

**Metrics**:
- **mean_score**: Average score (1–5) across top-5 results per arm×level×category
- **p@5**: Fraction of top-5 results scoring ≥4
- **ndcg@5**: Normalized Discounted Cumulative Gain (accounts for ranking quality)

**Judgment Criteria** (DESIGN §0, adjusted for 14-song sample):
- **Adopt Candidate**: All 4 categories mean ≥3.5 AND 3/4 categories with p@5 ≥0.4
- **Conditional Retry**: 2.5–3.5 range → investigate causes (ASR quality, embedding model, pool size)
- **Reject**: <2.5

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | (env or work/groq.key) | Groq LLM API key |
| `WHISPER_MODEL` | medium | faster-whisper model size (tiny/base/small/medium/large-v3) |
| `GROQ_MODEL` | llama-3.3-70b-versatile | Groq model to use |

---

## File Structure

```
method-1/
├── README.md                    # This file
├── DESIGN.md                    # Technical specification (research design)
├── config.py                    # All constants (do not modify DESIGN.md values)
├── requirements.txt
├── .gitignore                   # Ignores work/ and transcripts
├── 00_prepare_stems.py          # Vocal separation (demucs)
├── 01_transcribe.py             # ASR transcription (faster-whisper)
├── 02_build_texts.py            # LLM text generation (Groq)
├── 03_embed.py                  # Embedding (sentence-transformers)
├── 04_search.py                 # Cosine search & eval sheet generation
├── 05_analyze.py                # Metrics & judgment
├── _demucs_run.py               # Demucs runner (torchaudio shim)
├── out/                         # Output CSVs & embeddings (committed)
│   ├── transcripts_meta.csv
│   ├── texts_summary.csv
│   ├── texts_keyword.csv
│   ├── queries_expanded.csv
│   ├── embeddings.npz
│   ├── results_top5.csv
│   ├── eval_sheet.csv           # Blind form (human fills in scores)
│   ├── eval_mapping.csv
│   └── analysis_summary.csv
└── work/                        # Gitignored
    ├── stems/<tag>/vocals.wav   # Vocal stems
    ├── transcripts/<tag>.txt    # ASR lyrics (not committed)
    ├── groq.key                 # API key (not committed)
    └── htdemucs_temp/           # Demucs temporary output
```

---

## Known Limitations (§8 of DESIGN.md)

1. **Small pool size**: 14 songs (sample run) → limited search variance; 30 songs (full run) still smaller than ideal
2. **No acoustic features**: Lyrics alone, no tempo/energy/acousticness matching
3. **Single evaluator**: Blind form removes arm bias, but personal taste bias remains
4. **ASR errors**: Not quantified; only spot-checked via QC
5. **Unified evaluation baseline**: L4 prompt used for all categories → L1 queries may be systematically disadvantaged (see RQ2 analysis)

---

## Contact & Issues

For questions or issues:
1. Check DESIGN.md §0 (research questions) and §9 (open questions)
2. Verify config.py constants match DESIGN §5/§7
3. Re-run from the problematic step with verbose output

---

## Citation

This experiment is part of the lyrics vector search research pipeline. Results and methodology are documented in the research-branch notes under `topic/vector-embedding/`.
