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

**Scoring scale**:
- 1: Doesn't match at all
- 2: Poor match
- 3: Acceptable match
- 4: Good match
- 5: Excellent match

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
