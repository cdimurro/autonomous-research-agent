# Phase 10K: Adoption Decision

**Date:** 2026-03-14
**Branch:** `breakthrough-engine-phase10k-graph-native-rollout`

## Decision

**`ready_to_merge_and_adopt`**

## Rationale

The Phase 10K burn-in (3 eval + 3 prod campaigns) confirms that graph-native
retrieval via HybridKGEvidenceSource holds up in production-like use:

| Check | Result |
|-------|--------|
| Score preserved (>= -0.01 vs baseline) | PASS (-0.0018) |
| Score above rollback (>= -0.05) | PASS (-0.0018) |
| Approval >= 60% | PASS (100%) |
| Approval above rollback (>= 40%) | PASS (100%) |
| No systematic failures (<= 1) | PASS (0 failures) |
| Persistence >= 90% | PASS (100%) |

## Evidence Trail

1. **Phase 10J A/B (7+7):** Graph-native 0.9163 vs Current 0.9059 (+0.0104),
   100% approval both arms, 8.7 vs 2.0 unique sources. All 6 threshold checks
   pass for the first time across four A/B phases (10G-10J).

2. **Phase 10K burn-in (3+3):** Mean score 0.9108 (vs baseline 0.9126, delta
   -0.0018 within -0.01 tolerance). 100% approval (vs baseline 83.3%). 9.0
   unique sources (vs baseline 2.0). 100% persistence. 0 failures.

3. **Root cause resolution:** The Phase 10J fixes (evidence_refs diversity
   fallthrough + source-aware hybrid pool) resolved the diversity failure that
   persisted through Phases 10G-10I. These fixes are stable across 20 campaigns
   (14 A/B + 6 burn-in).

## What This Means

- The rollout branch `breakthrough-engine-phase10k-graph-native-rollout` is
  ready to merge to main when the team decides to adopt graph-native retrieval
  as the permanent production default.
- No merge has been performed — this decision is advisory only.
- Rollback path is verified and documented in `PHASE10K_ROLLBACK.md`.

## Baseline Frozen

New production baseline frozen at:
`runtime/baselines/phase10k_graph_native_production_baseline_regime2.json`

This supersedes `phase9e_promoted_production_regime2` as the production
reference for graph-native retrieval. The prior baseline is retained as the
rollback anchor.

## Constraints Honored

- No merge to main
- Fixed policy (evidence_diversity_v1)
- Fixed embedding (qwen3-embedding:4b)
- Fixed generation (qwen3.5:9b-q4_K_M)
- No policy challengers
- All tests offline-safe
