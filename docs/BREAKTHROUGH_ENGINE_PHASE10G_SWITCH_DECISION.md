# Phase 10G: Switch Decision

**Date:** 2026-03-13
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`

## Decision: `continue_limited_ab`

## Evidence Summary

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean champion score | 0.9042 | **0.9079** | **+0.004** |
| Approval rate | 100% | 100% | 0 |
| Campaigns completed | 6/6 | 6/6 | |
| Mean finalists | 6.5 | 7.0 | +0.5 |
| Evidence pack diversity | 2.0 | 1.0 | -1.0 |
| Mean elapsed (s) | 1020 | 1111 | +9% |

## Threshold Check Results

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| Score preservation (>= -0.01) | -0.01 | +0.004 | **PASS** |
| Score above rollback (>= -0.05) | -0.05 | +0.004 | **PASS** |
| Approval >= 60% | 60% | 100% | **PASS** |
| Approval above rollback (>= 40%) | 40% | 100% | **PASS** |
| Diversity >= current | >= 2.0 | 1.0 | **FAIL** |
| No systematic failures | <= 1 | 0 | **PASS** |

5/6 checks pass. The only failure is in-pipeline evidence diversity.

## Rationale

**Why not `promote_graph_native_retrieval`:**
The diversity_ge_current check fails. Evidence packs in graph-native campaigns
have fewer unique source IDs than current. While graph-native produces more
topically diverse *champion hypotheses*, the measured in-pipeline evidence
diversity is lower. This may be a measurement artifact (KG items sharing
source IDs) rather than a real diversity regression, but the check fails
and promotion requires all checks to pass.

**Why not `keep_current_retrieval`:**
Graph-native exceeds all rollback thresholds by wide margins:
- Score is +0.004 above current (well above -0.05 rollback trigger)
- Approval is 100% (well above 40% rollback trigger)
- Zero failures
- Champion topic diversity is qualitatively better

**Why `continue_limited_ab`:**
The results are strongly positive but one check fails. The correct next step
is to investigate whether the evidence diversity measurement is accurate or
an artifact, and if accurate, whether KG evidence source ID sharing can be
fixed. A second A/B round with corrected diversity measurement would give
a clear promotion/rejection signal.

## Next Steps

1. **Investigate evidence pack diversity measurement** — check if KG evidence
   items share source_ids (which would make the diversity metric misleading)
2. **If measurement artifact:** fix the metric and re-run comparison
3. **If real regression:** investigate why HybridKGEvidenceSource reduces
   source diversity in evidence packs despite providing more diverse retrieval
4. **After investigation:** run a follow-up 6+6 A/B with corrected metrics
5. **Do not promote or switch** until diversity check passes or is explicitly waived

## Manual Promotion Steps (If Later Recommended)

If a future A/B clears all checks, the exact steps to promote would be:

1. In production `LadderConfig`, set:
   - `evidence_source_override = HybridKGEvidenceSource(...)`
   - `enable_graph_context = True`
2. Run 3 production campaigns to verify stability
3. Monitor for 48 hours
4. If approval stays >= 60%, consider permanent

## Rollback

Remove `evidence_source_override` and `enable_graph_context` from LadderConfig.
The pipeline immediately reverts to ExistingFindingsSource + flat template.
No database migration needed. No embedding change needed.
