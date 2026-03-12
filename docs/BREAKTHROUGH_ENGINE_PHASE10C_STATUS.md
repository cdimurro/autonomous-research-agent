# Phase 10C: Retrieval A/B Trial — Status

**Branch:** `breakthrough-engine-phase10a-kg-shadow`
**Base commit:** `43b00df` (Phase 10B)
**Date:** 2026-03-12
**Schema version:** 12 (unchanged)

## Summary

Phase 10C ran a controlled 6+6 retrieval A/B trial comparing current production retrieval (ExistingFindingsSource) against KG shadow retrieval (KGEvidenceSource) under a fixed champion policy (evidence_diversity_v1).

**Result:** KG arm underperformed. All threshold checks failed. Recommendation: `keep_shadow_only`.

## Key Findings

| Metric | Current Arm | KG Arm | Delta |
|--------|-------------|--------|-------|
| Mean champion score | 0.8741 | 0.8092 | -0.0649 |
| Approval rate | 100% | 0% | -100pp |
| Mean finalists | 3.0 | 2.5 | -0.5 |
| Campaigns completed | 6/6 | 5/6 (1 no-pub) | |

## Threshold Checks

| Threshold | Required | Actual | Result |
|-----------|----------|--------|--------|
| KG score >= current - 0.02 | >= 0.854 | 0.809 | FAIL |
| KG diversity >= current | >= 1.0 | 0.8 | FAIL |
| KG approval >= 60% | >= 60% | 0% | FAIL |
| KG score above rollback | >= 0.824 | 0.809 | FAIL |
| KG approval above rollback | >= 40% | 0% | FAIL |

## Recommendation

**`keep_shadow_only`** — KG arm triggered rollback criteria.

## Analysis

### Why KG retrieval scored lower
1. **Evidence quality gap**: KG segments have lower relevance scores (mean 0.49 vs 0.93 for production findings). While this reduces monoculture, the scoring pipeline penalizes lower-relevance evidence.
2. **KG evidence is structurally different**: kg_segment source_type may not integrate well with the current evidence_ranking_weights (which expect `paper`/`finding` types).
3. **Approval threshold**: All KG candidates scored 0.79-0.84, which falls below the 0.85 auto-approve threshold, resulting in 100% defer.
4. **Campaign 6 failure**: One KG campaign produced no publication (completed_no_publication), suggesting edge cases in KG evidence packs.

### What worked
- KG retrieval does run cleanly through the full pipeline
- KG campaigns produce viable candidates (0.79-0.84 range, not garbage)
- The score gap (-0.065) is moderate, not catastrophic
- KG evidence diversity at the segment level remains superior (Phase 10B confirmed 4x improvement)

### What needs fixing before retry
1. **Evidence relevance scoring**: KG segments need relevance re-calibration. Current scores (0.42-0.55) are too low relative to production findings (0.93).
2. **Evidence ranking integration**: evidence_ranking_weights may need tuning for kg_segment source_type.
3. **More extraction coverage**: Only 27/396 segments were extracted. Completing extraction may improve graph context quality.
4. **Hybrid retrieval**: Consider composing KG + existing findings rather than pure KG replacement.

## Deliverable Status

| Deliverable | Status | Details |
|-------------|--------|---------|
| A: Phase 10B freeze | COMPLETE | Committed at 43b00df |
| B: Comparability check | COMPLETE | Only variable = evidence_source |
| C: 6+6 A/B batch | COMPLETE | 12 campaigns, 7268s total |
| D: Review labels | COMPLETE | 22 labels (12 current + 10 KG) |
| E: A/B comparison | COMPLETE | keep_shadow_only |
| F: Switch decision | COMPLETE | keep_shadow_only |
| G: Production safety | COMPLETE | Production untouched |

## Campaign Results

### Current Arm
| # | Score | Finalists | Status |
|---|-------|-----------|--------|
| 1 | 0.8907 | 3 | completed |
| 2 | 0.8607 | 3 | completed |
| 3 | 0.8607 | 3 | completed |
| 4 | 0.8907 | 3 | completed |
| 5 | 0.8607 | 3 | completed |
| 6 | 0.8807 | 3 | completed |

### KG Arm
| # | Score | Finalists | Status |
|---|-------|-----------|--------|
| 1 | 0.7992 | 3 | completed |
| 2 | 0.7992 | 3 | completed |
| 3 | 0.8392 | 3 | completed |
| 4 | 0.8092 | 3 | completed |
| 5 | 0.7992 | 3 | completed |
| 6 | 0.0000 | 0 | completed_no_publication |

## Production Impact

**ZERO** — no production code modified. All campaigns ran on the shadow branch with no effect on live production.

## Artifacts

All in `runtime/phase10c/`:
- `comparability_check.json`
- `arm_summary.json`, `arm_summary.md`
- `champions.csv`, `campaign_metrics.csv`
- `review_labels.csv`
- `label_completion_summary.json`
- `comparison_summary.json`, `comparison_summary.md`
- `manifest.json`

## Next Steps

1. Re-calibrate KG segment relevance scoring
2. Complete extraction on remaining 369 scored segments
3. Consider hybrid retrieval (KG + existing findings composite)
4. Tune evidence_ranking_weights for kg_segment source_type
5. Re-run A/B trial after fixes
