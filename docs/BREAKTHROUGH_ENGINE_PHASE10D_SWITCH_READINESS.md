# Phase 10D Switch-Readiness Decision

## Recommendation

**`ready_for_limited_production_retrieval_ab`**

Hybrid retrieval preserves score quality while improving source-type diversity. Recommend a bounded production A/B trial.

## Threshold Checks

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| Score preservation | >= 0.8693 | 0.8725 | PASS |
| Diversity (unique sources) | >= 11 | 11 | PASS |
| Source type diversity | >= 1 type | 2 types | PASS |

## Evidence Base

### Strengths
1. Hybrid mean relevance 0.8725 — within 0.01 of current (0.8793)
2. Two source types (finding + kg_segment) vs one (finding only)
3. Top-1 concentration reduced to 13.3%
4. Calibration is explainable and logged
5. All 1041 tests pass; no production code modified

### Limitations
1. Campaign-level comparison not yet run (requires live Ollama)
2. KG extraction only 27/396 segments — more extraction may improve hybrid quality
3. Unique source_id count unchanged (11=11) — KG adds type diversity, not necessarily more source IDs

## Prescribed Next Experiment

| Parameter | Value |
|-----------|-------|
| Design | 3+3 or 5+5 campaign A/B |
| Arms | Current retrieval vs Hybrid retrieval |
| Policy | evidence_diversity_v1 (champion, fixed) |
| Profile | evaluation_daily_clean_energy |
| Success | hybrid score >= current - 0.01, approval >= 60% |
| Rollback | hybrid score < current - 0.05 or approval < 40% |

## What Must NOT Happen

- No production retrieval switch without campaign trial completion
- No merge to main
- No policy change during trial
