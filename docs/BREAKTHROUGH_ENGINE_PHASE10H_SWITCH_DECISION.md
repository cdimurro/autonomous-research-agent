# Phase 10H: Switch Decision

**Date:** 2026-03-14
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`

## Decision: `continue_limited_ab`

## Evidence Summary

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean champion score | 0.9084 | **0.9098** | **+0.0014** |
| Approval rate | 100% | 100% | 0 |
| Campaigns completed | 7/7 | 7/7 | |
| Mean finalists | 6.4 | 6.9 | +0.5 |
| Mean evidence items | 2.0 | 2.0 | 0 |
| Mean unique sources | 2.0 | 1.0 | -1.0 |
| Mean elapsed (s) | 952 | 909 | -4.5% |

## Threshold Check Results

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| Score preservation (>= -0.01) | -0.01 | +0.0014 | **PASS** |
| Score above rollback (>= -0.05) | -0.05 | +0.0014 | **PASS** |
| Approval >= 60% | 60% | 100% | **PASS** |
| Approval above rollback (>= 40%) | 40% | 100% | **PASS** |
| Diversity >= current | >= 2.0 | 1.0 | **FAIL** |
| No systematic failures | <= 1 | 0 | **PASS** |

5/6 checks pass. The only failure is evidence pack diversity.

## Root Cause Analysis of Diversity Failure

Phase 10G diagnosed this as a measurement artifact (paper-level source_ids).
Phase 10H applied the fix (segment-level source_ids). The check **still fails**.

The actual root cause is deeper:

1. **Evidence packs are small**: Each candidate gets only 2 items (`evidence_minimum=2`)
2. **Evidence items stored sparsely**: Only 1 of 7-8 packs per run has items in
   `bt_evidence_items` (244/1589 packs have stored items)
3. **Ranking concentrates sources**: `rank_evidence()` selects by mechanism relevance,
   not source diversity. For graph-native candidates, the top-2 mechanism-matched items
   both come from `arxiv:2402.11234`. For current candidates, they come from 2 papers.
4. **Retrieval IS diverse**: HybridKGEvidenceSource reports `unique_sources=5` in its
   output, but the ranking narrows this to 1-2 papers in the final pack.

The source_id fix (Deliverable A) was correct but insufficient — it addressed the wrong
layer. The diversity gap is in evidence **ranking**, not evidence **retrieval**.

## Phase 10G vs 10H Comparison

| Metric | Phase 10G | Phase 10H |
|--------|-----------|-----------|
| Campaigns per arm | 6 | 7 |
| Score delta | +0.004 | +0.0014 |
| Approval | 100% / 100% | 100% / 100% |
| Diversity check | FAIL | FAIL |
| Diversity root cause | Paper-level source_ids | Evidence ranking concentration |
| Graph caching | No | Yes |
| Elapsed (graph arm) | 1111s | 909s (-18%) |

Graph caching reduced graph-native elapsed time by ~18%.

## Rationale

**Why not `promote_graph_native_retrieval`:**
The diversity check fails. While the root cause is in evidence ranking (not retrieval),
and the score/approval signals are strong, promotion requires all checks to pass.

**Why not `keep_current_retrieval`:**
Graph-native exceeds all rollback thresholds by wide margins:
- Score is +0.0014 above current (well above -0.05 rollback trigger)
- Approval is 100% (well above 40% rollback trigger)
- Zero failures across 7 campaigns
- Graph-native elapsed is actually faster (909s vs 952s) due to caching

**Why `continue_limited_ab`:**
Strong quality signal, but the diversity check reveals a real (though narrow) gap in
how evidence items are selected. Two options for next steps:

1. **Fix evidence ranking**: Add diversity-aware tie-breaking to `rank_evidence()` so
   it doesn't concentrate on one source when multiple are equally relevant
2. **Waive the diversity check**: The diversity gap is in pack construction (2 items),
   not retrieval (5+ sources). If diversity-aware ranking is deemed low priority, the
   check could be explicitly waived for promotion.

## Next Steps

1. **Investigate `rank_evidence()` diversity**: Does it offer any source diversity
   consideration? If not, add a diversity bonus to the ranking composite score.
2. **Fix evidence item storage**: Only 1/7 packs store items → `bt_evidence_items`
   is mostly empty. Fix the storage path so all packs persist their items.
3. **If ranking fix applied**: Run a follow-up 6+6 A/B to verify diversity check passes
4. **If waiving diversity**: Document the waiver rationale and promote manually

## Manual Promotion Steps (If Later Recommended)

Same as Phase 10G:
1. In production `LadderConfig`, set:
   - `evidence_source_override = HybridKGEvidenceSource(...)`
   - `enable_graph_context = True`
2. Run 3 production campaigns to verify stability
3. Monitor for 48 hours
4. If approval stays >= 60%, consider permanent

## Rollback

Remove `evidence_source_override` and `enable_graph_context` from LadderConfig.
No database migration needed. No embedding change needed.
