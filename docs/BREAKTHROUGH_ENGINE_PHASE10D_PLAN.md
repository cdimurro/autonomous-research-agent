# Phase 10D: KG Hardening Plan

## Objective

Harden the KG as a calibrated hybrid evidence layer that can materially improve the pipeline, rather than treating it as a direct replacement for production retrieval.

## Strategy

1. Diagnose why pure KG lost in Phase 10C (root-cause audit)
2. Implement source-aware score calibration so KG evidence competes fairly
3. Build hybrid retrieval (trusted findings + KG diversification)
4. Add source-type awareness to evidence ranking
5. Compare current / KG / hybrid at retrieval level
6. Produce switch-readiness recommendation

## Key Insight

Pure KG replacement was too aggressive. The score scale mismatch (KG mean 0.584 vs finding mean 0.874) made KG evidence look weak even when it provided better diversity. The fix is calibration + hybrid composition, not abandoning KG.

## Constraints

- No production retrieval switch
- No merge to main
- Evidence_diversity_v1 policy fixed
- Shadow-only KG work
- All tests offline-safe
