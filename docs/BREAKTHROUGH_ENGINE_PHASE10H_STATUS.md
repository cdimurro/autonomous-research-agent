# Phase 10H: Diversity Metric Hardening, Graph Caching, Extended A/B — Status

**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Date:** 2026-03-14

## Deliverable Status

| Deliverable | Status |
|-------------|--------|
| A: Diversity metric hardening | COMPLETE |
| B: Graph caching | COMPLETE |
| C: Comparability lock re-check | COMPLETE |
| D: Extended A/B execution (7+7) | COMPLETE |
| E: Review label collection | COMPLETE (28 labels) |
| F: Comparison summary | COMPLETE |
| G: Switch decision | COMPLETE (`continue_limited_ab`) |
| H: Rollback readiness | COMPLETE |
| I: Testing | COMPLETE (1142 passing) |
| J: Artifact packaging | COMPLETE |
| K: Commit | PENDING |

## Key Results

- **Score**: Graph-native 0.9098 vs Current 0.9084 (+0.0014)
- **Approval**: Both 100%
- **Diversity check**: FAIL (evidence ranking concentration, not retrieval)
- **Graph caching**: 18% elapsed reduction for graph-native arm
- **Recommendation**: `continue_limited_ab`
- **Tests**: 1142 passing, 0 failures
- **Production default**: Unchanged

## Root Cause Update

Phase 10G diagnosed the diversity failure as paper-level source_ids (measurement
artifact). Phase 10H fixed that (Deliverable A) but the check still fails.

Actual root cause: `rank_evidence()` selects top-2 mechanism-matched items which
concentrate on `arxiv:2402.11234`. The retrieval layer IS diverse (5+ unique sources)
but the ranking layer narrows it. Additionally, only 1/7 evidence packs store items
to `bt_evidence_items`, making the measurement sparse.

## Artifacts

- `runtime/phase10h/arm_summary.json`
- `runtime/phase10h/comparison_summary.json`
- `runtime/phase10h/comparison_summary.md`
- `runtime/phase10h/champions.csv`
- `runtime/phase10h/campaign_metrics.csv`
- `runtime/phase10h/review_labels.csv`
- `runtime/phase10h/label_completion_summary.json`
- `runtime/phase10h/label_completion_summary.md`
- `runtime/phase10h/comparability_report.json`
