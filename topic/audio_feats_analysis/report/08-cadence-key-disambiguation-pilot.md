# Report 08: Cadence-based Key Disambiguation Pilot

## Objective
Test whether chord progression cadence analysis can disambiguate between the top-2 K-S key candidates.
Background: Krumhansl-Schmuckler correlation cannot distinguish closely-related keys (e.g., A minor ↔ G major,
differing by only 1 pitch in the diatonic scale).

## Hypothesis
Two key candidates related by a perfect 5th (differing by one accidental pitch) can be distinguished by analyzing:
1. **Final chord**: Does the song end on the tonic triad of candidate 1 or 2?
2. **V→I cadences**: Are dominant→tonic progressions more prevalent in candidate 1 or 2?

## Dataset
- **17 songs** from *morfonica* band (K-S estimated key = A minor)
- **4 songs with ground truth** (verified via tunebat.com / Spotify)
- **13 songs unverified** (ground truth unknown)

## Methodology
For each song and each K-S candidate (best and 2nd):
1. Extract beat-aligned chord sequence (cosine similarity vs. triad templates)
2. **Final chord score** (+3): Majority chord in last 4 beats matches tonic triad
3. **V→I cadence count** (+1 each): Count of "dominant major → tonic" transitions
4. **Cadence pick**: Candidate with higher combined score (ties favor K-S best)

## Results

### Summary Statistics
- **Total songs**: 17
- **Songs where cadence changed the pick**: 3 (17.6%)
- **Ground truth accuracy (before)**: 2/4 (50%) — Wingbeat, 輪舞-revolution correct; flame of hope, Angel's Ladder wrong
- **Ground truth accuracy (after)**: 1/4 (25.0%)

### Songs with Changed Decisions
- **morfonica__202** (Angel's Ladder) K-S: Amin -> Cadence: Fmaj | Ground: Bbmaj [FAIL]
- **morfonica__221** (輪舞-revolution (Cover)) K-S: Amin -> Cadence: Amaj | Ground: Amin [FAIL]
- **morfonica__226** (chAngE (Cover)) K-S: Amin -> Cadence: A#maj

### Ground Truth Evaluation (4 songs)
- [FAIL] **morfonica__182** (flame of hope): Ground=Gmaj, K-S best=Amin, Cadence pick=Amin
- [OK] **morfonica__191** (誓いのWingbeat): Ground=Amin, K-S best=Amin, Cadence pick=Amin
- [FAIL] **morfonica__202** (Angel's Ladder): Ground=Bbmaj, K-S best=Amin, Cadence pick=Fmaj
- [FAIL] **morfonica__221** (輪舞-revolution (Cover)): Ground=Amin, K-S best=Amin, Cadence pick=Amaj

## Conclusion
Cadence analysis shows **no improvement**: 1/4 ground truth songs correct (vs. 2/4 baseline). 3 songs changed decisions but accuracy declined. Consider alternative approaches (e.g., temporal cadence patterns, tonic harmony emphasis).

## Next Steps
1. **Expand ground truth**: Manually verify 5-10 more songs from changed decisions
2. **Refine V→I detection**: Consider harmonic minor V (dominant seventh) patterns
3. **Full evaluation**: If accuracy improves on ground truth, extend to all 661 songs
