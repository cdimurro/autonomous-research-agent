# Phase 10H: Rollback Guardrails

**Date:** 2026-03-13
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`

## Production Default

**Unchanged.** The production pipeline uses `ExistingFindingsSource` + flat generation
template. Graph-native retrieval is experiment-only via `LadderConfig` overrides.

## Rollback Scope

Phase 10H changes two files:

1. **`breakthrough_engine/kg_retrieval.py`** — segment-level source_ids
   - Affects KG evidence diversity measurement only
   - No impact on production retrieval (KGEvidenceSource is not used in production path)
   - Rollback: revert to `source_id=seg.get("source_id", seg.get("paper_id", ""))`

2. **`breakthrough_engine/orchestrator.py`** — graph caching
   - Affects graph context construction performance only
   - No impact when `enable_graph_context=False` (production default)
   - Rollback: remove `_graph_cache` class variable and restore original `_build_graph_context()`

## Reverting the A/B Experiment

If the A/B experiment produces negative results:

1. Do NOT set `evidence_source_override` or `enable_graph_context` in production `LadderConfig`
2. The pipeline immediately uses `ExistingFindingsSource` + flat template (default)
3. No database migration needed
4. No embedding change needed

## Mandatory Rollback Triggers

Same as Phase 9E/10G:
- Approval rate < 40% over 6 consecutive graph-native runs
- Score delta < -0.05 compared to current arm mean

## If Promotion Is Later Recommended

See `docs/BREAKTHROUGH_ENGINE_PHASE10G_SWITCH_DECISION.md` for manual promotion steps.
The same steps apply — the only change is that diversity metrics are now correctly measured.
