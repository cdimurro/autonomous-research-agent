# Phase 10K: Rollback / Reversion Readiness

**Branch:** `breakthrough-engine-phase10k-graph-native-rollout`
**Date:** 2026-03-14

## Rollback Target

Revert to the prior production retrieval path:
- **Evidence source:** ExistingFindingsSource + Semantic Scholar (CompositeRetrievalSource)
- **Graph context:** disabled
- **Policy:** evidence_diversity_v1 (unchanged)
- **Baseline:** `phase9e_promoted_production_regime2` (mean 0.9126, approval 83.3%)

## Rollback Triggers

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Approval collapse | < 40% over 6 consecutive runs | Mandatory rollback |
| Score regression | < 0.85 mean (> -0.06 below Phase 9C baseline) | Mandatory rollback |
| Reject rate spike | >= 3/6 consecutive champions rejected | Mandatory rollback |
| Integrity failures | integrity_status != ok for 3 consecutive eval runs | Mandatory rollback |
| Approval soft decline | 50-60% over 6 runs | Investigate first |
| Score delta < -0.05 sustained | Over 6 runs vs baseline | Mandatory rollback |

## Rollback Procedure

### Option A: Code reversion (minimal)

Remove the graph-native retrieval wiring from `campaign_manager.py`:

1. Remove the `HybridKGEvidenceSource` construction block (lines added in Phase 10K)
2. Remove `evidence_source_override=graph_native_source` from LadderConfig
3. Remove `enable_graph_context=True` from LadderConfig
4. Remove the 3 new imports (`ExistingFindingsSource`, `HybridKGEvidenceSource`, `KGEvidenceSource`)

The orchestrator will then fall back to its default retrieval path
(ExistingFindingsSource or CompositeRetrievalSource with Semantic Scholar).

### Option B: Branch reversion (complete)

```bash
git checkout breakthrough-engine-phase10g-retrieval-ab
```

This returns to the exact state before graph-native promotion, with all
Phase 10J fixes in place but graph-native retrieval not wired as default.

### Option C: Selective revert (preserve evidence_refs fix)

The evidence_refs diversity check in `orchestrator.py` is harmless when no
graph-native source is used — diverse refs are preserved as-is. So this fix
can remain even after rollback.

## What Is Preserved After Rollback

- All Phase 10J fixes (evidence_refs diversity check, source-aware pool construction)
- All Phase 10I fixes (diversity-aware ranking, persistence fix)
- All burn-in artifacts in `runtime/phase10k/`
- Champion policy `evidence_diversity_v1`
- KG corpus and graph data

## Dry-Run Verification

The rollback path was verified by confirming that:
1. The prior branch `breakthrough-engine-phase10g-retrieval-ab` exists and is clean
2. Campaign manager without the Phase 10K wiring uses default retrieval (verified in Phase 10J A/B current arm)
3. The evidence_refs diversity check is benign when evidence_refs are already diverse
