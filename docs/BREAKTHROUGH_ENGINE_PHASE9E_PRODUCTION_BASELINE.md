# Phase 9E Production Baseline: evidence_diversity_v1 (Regime 2)

**Baseline ID**: `phase9e_promoted_production_regime2`
**Phase**: 9E
**Date**: 2026-03-12
**Status**: FROZEN

---

## Overview

This is the first production baseline anchored to the promoted policy `evidence_diversity_v1`. It supersedes `phase9c_operational_regime2` (which was anchored to `phase5_champion`) as the primary Regime 2 production reference.

All future Phase 10+ challenger comparisons should use this baseline as their anchor, not the Phase 9C baseline.

---

## Baseline Coordinates

| Parameter | Value |
|-----------|-------|
| Baseline ID | `phase9e_promoted_production_regime2` |
| Champion policy | `evidence_diversity_v1` |
| Prior champion policy | `phase5_champion` |
| Branch | `breakthrough-engine-phase9c-challenger-iteration` |
| Commit | `ec715e4` |
| Embedding model | `qwen3-embedding:4b` (2560d, Regime 2) |
| Generation model | `qwen3.5:9b-q4_K_M` |
| Date | 2026-03-12 |

---

## Aggregate Metrics

| Metric | Eval (3 runs) | Prod (3 runs) | Combined (6 runs) |
|--------|--------------|---------------|-------------------|
| Mean champion score | 0.9172 | 0.9080 | **0.9126** |
| Min score | 0.9105 | 0.8930 | 0.8930 |
| Max score | 0.9205 | 0.9205 | 0.9205 |
| Approval rate | 100% | 66.7% | **83.3%** |
| Mean novelty | 0.860 | 0.847 | **0.853** |
| Mean plausibility | 0.860 | 0.850 | **0.855** |
| Integrity OK | 3/3 | 3/3 | 6/6 |

---

## Comparison to Superseded Baseline

| Metric | phase9c_operational (phase5_champion) | phase9e_promoted (evidence_diversity_v1) | Δ |
|--------|--------------------------------------|------------------------------------------|---|
| Mean score | 0.905 | 0.9126 | +0.008 |
| Approval rate | 66.7% | 83.3% | +16.7pp |
| Novelty | 0.837 | 0.853 | +0.016 |
| Plausibility | 0.847 | 0.855 | +0.008 |

---

## Baseline Hierarchy (Regime 2)

| Baseline | Policy | Date | Status |
|----------|--------|------|--------|
| phase9_new_embedding_reviewed | phase5_champion | 2026-03-10 | Archived (early Regime 2) |
| phase9c_operational_regime2 | phase5_champion | 2026-03-11 | Archived (prior anchor) |
| **phase9e_promoted_production_regime2** | **evidence_diversity_v1** | **2026-03-12** | **CURRENT** |

---

## Use Cases

1. **Phase 10 challenger A/B trial anchor**: New challengers are measured against this baseline (evidence_diversity_v1 mean score 0.9126, approval 83.3%).
2. **Regression detection**: Any future pipeline change that drops combined mean below 0.88 or approval below 60% should be flagged.
3. **Rollback reference**: If evidence_diversity_v1 is rolled back in the future, the Phase 9C baseline serves as the Regime 2 champion reference.

---

## Artifact Reference

```
runtime/baselines/phase9e_promoted_production_baseline_regime2.json
```

---

## Quality Gate Thresholds (for Future Use)

| Gate | Threshold | Current Value | Headroom |
|------|-----------|---------------|---------|
| Mean score | ≥ 0.88 | 0.9126 | +0.033 |
| Approval rate | ≥ 0.60 | 0.833 | +0.233 |
| Integrity OK | 100% | 100% | — |
| Max score regression | ≤ -0.05 vs baseline | — | — |
