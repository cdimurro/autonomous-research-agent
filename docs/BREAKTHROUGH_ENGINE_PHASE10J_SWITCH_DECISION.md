# Phase 10J: Switch Decision

**Date:** 2026-03-14
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`

## Decision

**`promote_graph_native_retrieval`**

## Rationale

All 6 threshold checks pass for the first time across four phases of A/B testing
(10G, 10H, 10I, 10J):

| Check | Result | Value |
|-------|--------|-------|
| Score preservation (>= -0.01) | PASS | +0.0104 |
| Score above rollback (>= -0.05) | PASS | +0.0104 |
| Approval >= 60% | PASS | 100% |
| Approval above rollback (>= 40%) | PASS | 100% |
| Diversity >= current | PASS | 8.7 vs 2.0 |
| No systematic failures | PASS | 0 failures |

## Key Metrics

| Metric | Current | Graph Native |
|--------|---------|-------------|
| Mean champion score | 0.9059 | 0.9163 (+0.0104) |
| Approval rate | 100% | 100% |
| Mean unique sources | 2.0 | 8.7 (+6.7) |
| Mean diversity score | 0.147 | 0.608 (+0.461) |
| Mean top concentration | 50.0% | 22.2% (-27.8%) |
| Persistence rate | 100% | 100% |

## What Changed in Phase 10J

Two fixes resolved the diversity failure that persisted through Phases 10G-10I:

1. **Evidence_refs diversity fallthrough** (orchestrator.py): When the generator's
   `evidence_refs` match items that all share the same `source_id`, the orchestrator
   now falls through to `rank_evidence()` + `select_diverse_top_k()` instead of
   using the non-diverse matched items directly.

2. **Source-aware hybrid pool** (hybrid_retrieval.py): `min_kg_items=2` reserves
   slots for KG items; `max_per_paper=3` caps per-source concentration;
   `_select_diverse_kg()` prefers items from distinct sources.

## Constraints on Promotion

Per the Phase 10J specification:
- Production default is **unchanged** by this experiment
- No merge to main
- Promotion requires a separate, deliberate action
- Rollback path: revert `HybridKGEvidenceSource` to `ExistingFindingsSource` +
  remove evidence_refs diversity check

## Rollback Readiness

- **Rollback target:** Current production retrieval (ExistingFindingsSource +
  Semantic Scholar, no graph context)
- **Rollback trigger:** approval rate < 40% over 6 consecutive runs, or
  score delta < -0.05 sustained
- **Rollback procedure:**
  1. Set `evidence_source_override=None` in production profiles
  2. Remove `graph_context=True` from DailySearchLadder config
  3. The evidence_refs diversity check in orchestrator.py is harmless when no
     graph-native source is used (diverse refs are preserved as-is)
- **Data preserved:** All Phase 10J artifacts in `runtime/phase10j/`
