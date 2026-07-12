# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status — BETA (live)

**This app is in BETA and serving real users** (beta launched 2026-07). It is well past the
"PRD only" stage: there is a working FastAPI backend (`src/backend/app`, hexagonal split — see
`docs/architecture.md`), a static frontend (`src/frontend`), and a pytest suite (`src/tests`, run
with `python -m pytest` from `src/`). `docs/PRD.md` + `docs/architecture.md` remain the source of
truth for scope, data model, and architectural constraints; don't invent stack choices that
contradict them (see "Open questions" below — several infra decisions are still undecided).

### Working agreement (IMPORTANT — beta is live)

Because the beta is serving users, **do not merge to `main` on your own.** For each task:

1. Create a **new branch** for that task.
2. Commit and push that branch.
3. **Open a PR against `main`, then stop.** The repo owner reviews the PR and merges it —
   you never merge `main` yourself, and you don't wait to be asked to open the PR.

## What this project is

`setlist-maker` (working repo name: bandori-playlist-maker) is a planned web app that generates
long-form listening setlists from a single natural-language request (e.g. "기분 좋아지는 1시간
플레이리스트"), using an LLM to extract mood/energy intent and harmonic-mixing rules (Camelot Wheel)
to sequence songs, then auto-plays them via YouTube iframe. It is a new, separate app from the sibling
project `bandori-song-sorter` (a static "browse" site), reusing that project's audio-feature dataset.

## 문서 취급 규칙 (중요)

`docs/ref/` 이하(특히 `docs/ref/user-opinion/`)는 **사용자가 세션에 전달하는 참조 문서**다.
**읽기 전용으로 참조만** 하고, 사용자의 **명시적 허락 없이 편집·삭제·이동·이름변경하지 말 것.**
브랜치 전환 등으로 워킹트리에서 보이지 않더라도 파일은 건드리지 말고, 필요한 내용은 인용·요약만 한다.

## Architecture mandated by the PRD (§8)

- **Clean/hexagonal split is required, not optional**: domain logic (mood-interpretation schema,
  energy-progression + harmonic-mixing selection rules) must not depend directly on any external
  service. LLM calls go through a port/interface with the LLM provider as a swappable adapter —
  switching OpenRouter models, or vendors entirely (e.g. to direct Anthropic/OpenAI calls), must be a
  single-adapter change.
- Selection logic must be a **pure function** over structured LLM output (mood/energy params) so it is
  unit-testable without calling any LLM.
- Workspace precedent to follow: `investbot`'s `src/core/adapter/` (protocol layer) →
  `src/core/api/` (business logic) separation.
- Needs a backend (not a static site) solely to hold the OpenRouter API key and (later) do request
  queuing — prefer a free tier with cold-start/sleep acceptable (Render et al., undecided).

## Data sources (reused from `bandori-song-sorter`, not this repo)

| Data | Location | Notes |
|---|---|---|
| YouTube URLs | `src/content/cluster/songs_full.csv` (`idx,band,song,url`, 660 rows) | `url` = `https://youtu.be/<video_id>`; needs a video_id parser (not yet built) |
| Mood features | `side-project/genre-features/song_features_with_proxies.csv` | `mode_score`, `energy_proxy`, `acousticness_proxy`, `instrumentalness_proxy`, `tempo_excerpt` (BPM) |
| Key (for harmonic mixing) | `key` column in the CSV above | `Amaj`/`Amin`-style, 24 values — needs a new Camelot Wheel mapping table |
| Auxiliary | `src/content/cluster/audio_map.json` | `songs[i] = {band, song, url, x, y, bpm, energy, shape}` |

These features were extracted for `bandori-song-sorter`'s EMOI-MAP pulse animation, not specifically
validated for mood-matching — PRD §6/§9 flags this as something to re-check during the pilot, and the
`key` column's pitch-detection accuracy is explicitly unverified (§7).

## Pilot scope (PRD §4) — must-have only

1. Natural-language request input.
2. OpenRouter LLM call → extract mood/energy direction (brightness, starting energy level).
3. Candidate filtering across the full song set (band checkbox filter is post-pilot).
4. Energy-progression logic: split the setlist into N stages (N default TBD — open question), pick
   per-stage by energy level, and prefer the next song whose key is Camelot-adjacent to the previous
   song's key.
5. Total playtime target (default 60 min, user-adjustable) determines song count.
6. Sequential YouTube iframe autoplay.

Explicitly out of pilot scope: saving/sharing as a real YouTube playlist (would need OAuth + Data API).

## Known open questions (PRD §9)

Treat these as unresolved — don't silently pick an answer when implementing related code without
flagging it: default/min/max energy stage count N; which OpenRouter model; hosting platform; when to
introduce request queuing; minimum sample-size threshold for excluding low-count bands (e.g. n<10,
poppin_party=115 vs. some bands=1); whether to surface "why this song was picked" explanations to
users; whether the reused audio features need re-extraction for mood-matching accuracy.
