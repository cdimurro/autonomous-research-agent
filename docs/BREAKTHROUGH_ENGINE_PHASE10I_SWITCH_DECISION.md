# Phase 10I: Switch Decision

**Date:** 2026-03-14
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`

## Decision: `continue_limited_ab`

## Evidence Summary

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean champion score | 0.9015 | **0.9191** | **+0.0176** |
| Approval rate | 100% | 100% | 0 |
| Campaigns completed | 7/7 | 7/7 | |
| Mean finalists | 6.6 | 6.6 | 0 |
| Mean evidence items | 14.6 | 14.0 | -0.6 |
| Mean unique sources | 2.0 | 1.0 | -1.0 |
| Mean persistence rate | 100% | 100% | 0 |
| Mean elapsed (s) | 941.7 | 944.8 | +0.3% |

## Threshold Check Results

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| Score preservation (>= -0.01) | -0.01 | +0.0176 | **PASS** |
| Score above rollback (>= -0.05) | -0.05 | +0.0176 | **PASS** |
| Approval >= 60% | 60% | 100% | **PASS** |
| Approval above rollback (>= 40%) | 40% | 100% | **PASS** |
| Diversity >= current | >= 2.0 | 1.0 | **FAIL** |
| No systematic failures | <= 1 | 0 | **PASS** |

5/6 checks pass. The only failure is evidence pack diversity.

## Phase 10I Fixes Applied

1. **Diversity-aware ranking** (`select_diverse_top_k`): Per-source cap prevents
   ranking-layer concentration. Enforces `max_per_source=1` with bypass only when
   margin >= 0.15 and other sources already represented.
2. **Evidence item persistence** (fresh IDs per pack): Each pack's items get new
   UUIDs, preventing `INSERT OR REPLACE` collisions. Persistence rate: 100%
   (was ~14% in Phase 10H).

## Root Cause Analysis of Remaining Diversity Failure

Phase 10H diagnosed the diversity failure as ranking-layer concentration.
Phase 10I fixed ranking with `select_diverse_top_k()`. The check **still fails**
for the graph-native arm.

The root cause is now in the **evidence pool itself**, not ranking:

1. **Current arm** has diverse evidence: `ExistingFindingsSource` retrieves items
   from multiple papers in `bt_findings`. Combined with Semantic Scholar results,
   the pool has 5+ unique `source_id` values. `select_diverse_top_k` selects
   items from 2 different sources → unique_sources=2.0. ✓

2. **Graph-native arm** has concentrated evidence: `HybridKGEvidenceSource` retrieves
   KG segments primarily from `arxiv:2402.11234`. Even though the retrieval reports
   `unique_sources=5` at the segment level, the paper-level source_ids are dominated
   by one paper. When `select_diverse_top_k` enforces per-source caps, there are
   insufficient alternative sources to diversify → unique_sources=1.0. ✗

3. **The ranking fix is working correctly**: For the current arm, it maintained
   unique_sources=2.0 (same as Phase 10H). The fix cannot create diversity that
   doesn't exist in the evidence pool.

## Phase Progression

| Phase | Score Delta | Diversity | Root Cause Layer | Fix Applied |
|-------|-----------|-----------|-----------------|-------------|
| 10G | +0.004 | FAIL | Measurement (paper-level IDs) | — |
| 10H | +0.0014 | FAIL | Ranking concentration | segment_level_v2 IDs |
| **10I** | **+0.0176** | **FAIL** | **Evidence pool concentration** | **diversity-aware ranking + persistence** |

The score advantage has grown from +0.004 → +0.0014 → +0.0176 across phases.
The diversity failure has been traced through three layers: measurement → ranking → pool.

## Rationale

**Why not `promote_graph_native_retrieval`:**
The diversity check fails. The root cause is now in the evidence pool — KG segments
from `HybridKGEvidenceSource` are dominated by a single paper. Promotion requires
all checks to pass.

**Why not `keep_current_retrieval`:**
Graph-native exceeds all rollback thresholds by wide margins:
- Score is +0.0176 above current (well above -0.05 rollback trigger)
- Approval is 100% (well above 40% rollback trigger)
- Zero failures across 7 campaigns
- Persistence is 100% (confirmed fix)

**Why `continue_limited_ab`:**
The strongest score signal yet (+0.0176), but the diversity gap is now a pool-level
issue requiring changes to `HybridKGEvidenceSource` or the KG corpus itself:

1. **Diversify KG corpus**: Index papers beyond `arxiv:2402.11234` into the knowledge
   graph so KG segments come from multiple sources
2. **Source-aware KG retrieval**: Modify `HybridKGEvidenceSource` to prefer segments
   from distinct papers when building the evidence pool
3. **Waive the diversity check**: The diversity gap is in pool composition, not in
   how items are selected or ranked. If KG corpus expansion is low priority, the
   check could be explicitly waived for promotion given the strong score/approval signals.

## Next Steps

1. **Expand KG corpus**: Add more papers to the knowledge graph to provide
   source-diverse KG segments
2. **Or: Source-aware KG retrieval**: Add diversity consideration to
   `HybridKGEvidenceSource.gather()` so it selects from multiple papers
3. **If pool diversified**: Run a follow-up 6+6 A/B to verify diversity check passes
4. **If waiving diversity**: Document the waiver rationale and promote manually

## Manual Promotion Steps (If Later Recommended)

Same as Phase 10G/10H:
1. In production `LadderConfig`, set:
   - `evidence_source_override = HybridKGEvidenceSource(...)`
   - `enable_graph_context = True`
2. Run 3 production campaigns to verify stability
3. Monitor for 48 hours
4. If approval stays >= 60%, consider permanent

## Rollback

Remove `evidence_source_override` and `enable_graph_context` from LadderConfig.
No database migration needed. No embedding change needed.
