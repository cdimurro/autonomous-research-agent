# Phase 10J: KG Corpus Diversification, Source-Aware Hybrid Retrieval — Status

**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Date:** 2026-03-14

## Deliverable Status

| Deliverable | Status |
|-------------|--------|
| A | Corpus concentration audit | COMPLETE |
| B | KG corpus breadth verification | COMPLETE (sufficient) |
| C | Source-aware hybrid pool construction | COMPLETE |
| D | Diversity-aware evidence_refs handling | COMPLETE |
| E | Hybrid selection diagnostics | COMPLETE |
| F | Comparability re-check | COMPLETE |
| G | Confirmatory A/B (7+7) | COMPLETE |
| H | Review label collection | COMPLETE (28 labels) |
| I | Final comparison summary | COMPLETE |
| J | Switch decision | COMPLETE (`promote_graph_native_retrieval`) |
| K | Rollback readiness | COMPLETE |
| L | Testing | COMPLETE (1171 passing) |
| M | Artifact packaging | COMPLETE |

## Key Results

- **Score**: Graph-native 0.9163 vs Current 0.9059 (+0.0104)
- **Approval**: Both 100%
- **Diversity**: Graph-native 8.7 unique sources vs Current 2.0 (+6.7)
- **Diversity score**: Graph-native 0.608 vs Current 0.147 (+0.461)
- **Top concentration**: Graph-native 22.2% vs Current 50.0% (-27.8%)
- **Persistence**: Both 100%
- **All threshold checks**: PASS (first time in 4 phases)
- **Recommendation**: `promote_graph_native_retrieval`
- **Tests**: 1171 passing, 0 failures
- **Production default**: Unchanged

## Root Cause Discovery

Phase 10J audit revealed the actual root cause of the diversity failure was
NOT the KG corpus itself (which has 390 papers), but two interacting bugs:

1. **evidence_refs bypass**: The generator sets `evidence_refs` on ALL candidates.
   When present, the orchestrator matches items directly, completely skipping
   `rank_evidence()` and `select_diverse_top_k()`. For graph-conditioned candidates,
   ALL refs pointed to items from arxiv:2402.11234.

2. **KG items excluded from pool**: HybridKGEvidenceSource's pure relevance sort
   excluded all KG items (calibrated 0.75-0.88 vs findings 0.81-0.93).

## Fixes Applied

1. **evidence_refs diversity check** (orchestrator.py): When matched items have
   fewer unique sources than top_k, fall through to ranked matching.

2. **Source-aware hybrid pool** (hybrid_retrieval.py):
   - `min_kg_items=2`: Reserve slots for KG items
   - `max_per_paper=3`: Cap per source_id in trusted items
   - `_select_diverse_kg()`: Prefer KG items from distinct sources

## Test Results

- 1171 tests passing (1160 existing + 11 new Phase 10J tests)
- Tests cover: evidence_refs diversity check, source-aware pool, per-paper cap,
  diverse KG selection, diagnostics, edge cases

## Artifacts

- `runtime/phase10j/arm_summary.json`
- `runtime/phase10j/comparison_summary.json`
- `runtime/phase10j/comparison_summary.md`
- `runtime/phase10j/champions.csv`
- `runtime/phase10j/campaign_metrics.csv`
- `runtime/phase10j/review_labels.csv`
- `runtime/phase10j/label_completion_summary.json`
- `runtime/phase10j/label_completion_summary.md`
- `runtime/phase10j/comparability_report.json`
- `docs/BREAKTHROUGH_ENGINE_PHASE10J_AB_RESULTS.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE10J_SWITCH_DECISION.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE10J_CORPUS.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE10J_HYBRID_SELECTION.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE10J_PLAN.md`
