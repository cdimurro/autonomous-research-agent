# Phase 10K: Graph-Native Retrieval Burn-in Summary

**Date:** 2026-03-14T22:33:40.131490+00:00
**Campaigns:** 6 (3 eval + 3 prod)
**Retrieval:** HybridKGEvidenceSource
**Policy:** evidence_diversity_v1

## Burn-in vs Prior Baseline

| Metric | Prior Baseline | Burn-in | Delta |
|--------|---------------|---------|-------|
| Mean champion score | 0.9126 | 0.9108 | -0.0018 |
| Approval rate | 83.3% | 100.0% | +0.167 |
| Mean unique sources | 2.0 | 9.0 | +7.0 |
| Persistence rate | — | 100.0% | — |
| Mean elapsed (s) | — | 891.2 | — |

## Health Checks

| Check | Result |
|-------|--------|
| score_preserved | PASS |
| score_above_rollback | PASS |
| approval_ge_60pct | PASS |
| approval_above_rollback | PASS |
| no_systematic_failures | PASS |
| persistence_ok | PASS |

## Recommendation: `ready_to_merge_and_adopt`

**Reason:** Burn-in healthy across all checks. Graph-native retrieval holds up in production-like use.
