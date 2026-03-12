# Phase 10C: Switch Decision

## Recommendation

**`keep_shadow_only`**

KG retrieval is NOT ready for production use. Keep it as shadow-only while the following fixes are applied.

## Evidence

- Score delta: -0.065 (fails -0.02 threshold, fails -0.05 rollback threshold)
- Approval rate: 0% (fails 60% threshold, fails 40% rollback threshold)
- Diversity at campaign level: 0.8 unique sources vs 1.0 (fails diversity threshold)
- 1/6 KG campaigns produced no publication

## Root Cause Analysis

The core issue is **relevance score calibration**. KG segments score 0.42-0.55 vs production findings at 0.93. This is not a real quality difference — production findings are inflated by monoculture (96.5% from one paper). But the scoring pipeline treats these scores at face value, penalizing KG evidence.

## Required Fixes (Priority Order)

1. **Re-calibrate KG relevance scores**: Normalize segment relevance to be comparable to finding relevance. Options:
   - Scale KG scores to match the findings distribution
   - Use embedding similarity to candidate topic rather than fixed domain anchor
   - Apply min-max normalization within the KG segment pool

2. **Hybrid retrieval**: Instead of pure KG replacement, compose KG segments WITH existing findings via CompositeRetrievalSource. This preserves high-quality findings while adding KG diversity.

3. **Complete extraction**: Only 27/396 segments extracted. Graph context enrichment is minimal without more extraction coverage.

4. **Tune evidence ranking**: evidence_ranking_weights may need a `kg_source_bonus` or adjusted `api_relevance` weight for kg_segment types.

## Next Phase

After fixes 1-2 are applied, re-run the 6+6 A/B trial. Expected that hybrid retrieval will score within 0.02 of current while maintaining diversity gains.

## Production Safety

Production retrieval remains unchanged. No production switch. Champion policy evidence_diversity_v1 continues as-is.
