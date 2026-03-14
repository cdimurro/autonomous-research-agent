# Phase 10I: Diversity-Aware Ranking, Persistence Fix, Confirmatory A/B — Status

**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Date:** 2026-03-14

## Deliverable Status

| Deliverable | Status |
|-------------|--------|
| A: Ranking diagnosis | COMPLETE |
| B: Diversity-aware ranking (`select_diverse_top_k`) | COMPLETE |
| C: Evidence item persistence fix | COMPLETE |
| D: Unit tests (18 tests) | COMPLETE |
| E: Confirmatory A/B execution (7+7) | COMPLETE |
| F: Review label collection | COMPLETE (28 labels) |
| G: Comparison summary | COMPLETE |
| H: Switch decision | COMPLETE (`continue_limited_ab`) |
| I: Rollback readiness | COMPLETE |
| J: Testing | COMPLETE (1160 passing) |
| K: Artifact packaging | COMPLETE |
| L: Commit | PENDING |

## Key Results

- **Score**: Graph-native 0.9191 vs Current 0.9015 (+0.0176)
- **Approval**: Both 100%
- **Persistence**: Both 100% (fixed from ~14%)
- **Diversity check**: FAIL (evidence pool concentration, not ranking)
- **Recommendation**: `continue_limited_ab`
- **Tests**: 1160 passing, 0 failures (1142 existing + 18 new)
- **Production default**: Unchanged

## Fixes Applied

### Diversity-Aware Ranking (Deliverable B)

Added `select_diverse_top_k()` to `retrieval.py`:
- Greedy selection with per-source cap (`max_per_source=1`)
- Bypass only when margin >= 0.15 and other sources already represented
- Relaxation fallback when caps prevent filling k
- Annotates items with `diversity_penalty`, `effective_score`, `source_capped`

### Evidence Item Persistence (Deliverable C)

Modified `orchestrator.py:_run_evidence_gate()`:
- Creates fresh `EvidenceItem` copies with `new_id()` for each pack
- Preserves content fields (`source_id`, `title`, `quote`, etc.)
- Eliminates `INSERT OR REPLACE` collisions in `bt_evidence_items`
- Persistence rate: 100% (was ~14%)

## Root Cause Progression

| Phase | Diversity Failure Layer | Fix |
|-------|----------------------|-----|
| 10G | Measurement (paper-level source_ids) | — |
| 10H | Ranking (top-k concentrates on one source) | segment-level source_ids |
| **10I** | **Evidence pool (KG corpus dominated by one paper)** | **diversity-aware ranking + persistence** |

The ranking fix is working correctly — it maintains diversity for the current arm
(unique_sources=2.0). The remaining failure is that the graph-native evidence pool
itself lacks source diversity (KG segments come primarily from `arxiv:2402.11234`).

## Artifacts

- `runtime/phase10i/arm_summary.json`
- `runtime/phase10i/comparison_summary.json`
- `runtime/phase10i/comparison_summary.md`
- `runtime/phase10i/champions.csv`
- `runtime/phase10i/campaign_metrics.csv`
- `runtime/phase10i/review_labels.csv`
- `runtime/phase10i/label_completion_summary.json`
- `runtime/phase10i/label_completion_summary.md`
- `runtime/phase10i/comparability_report.json`
