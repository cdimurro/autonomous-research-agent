# Breakthrough Engine Scoring Calibration

**Phase**: 7C
**Date**: 2026-03-09
**Branch**: breakthrough-engine-phase7c-telemetry-calibration

---

## Scope

This document records the scoring audit and minimal justified calibration changes made in Phase 7C.

---

## Audit: evidence_strength

### Problem observed

In campaign f01a0a7c72304481, the champion had:
- `evidence_strength = 0.98`
- `evidence_refs` = 2 items

Multiple other finalists also showed `evidence_strength` near 0.98–1.00 with similar ref counts.

The score was effectively saturated: whether a candidate had 2 refs or 10 refs, the evidence_strength score barely differed.

### Current formula (Phase 7B)

```python
avg_relevance = sum(i.relevance_score for i in evidence_pack.items) / len(evidence_pack.items)
diversity_bonus = min(0.2, evidence_pack.source_diversity_count * 0.05)
score.evidence_strength_score = min(1.0, avg_relevance + diversity_bonus)
```

Example with 2 refs at 0.9 relevance:
- avg_relevance = 0.9
- diversity_bonus = 0.05 (1 source type)
- **evidence_strength = 0.95**

Example with 8 refs at 0.9 relevance:
- avg_relevance = 0.9
- diversity_bonus = 0.20
- **evidence_strength = 1.0**

Spread: 0.05 — not discriminative enough.

### Calibration change (Phase 7C)

Added a count-based penalty multiplier:

| Evidence count | Penalty multiplier |
|---------------|-------------------|
| 1 ref | 0.70 |
| 2 refs | 0.82 |
| 3 refs | 0.91 |
| 4 refs | 0.96 |
| 5+ refs | 1.00 (no penalty) |

New formula:
```python
count_penalty = {1: 0.70, 2: 0.82, 3: 0.91, 4: 0.96}.get(n_items, 1.0) if n_items <= 4 else 1.0
evidence_strength_score = round(raw_score * count_penalty, 6)
```

### Before/after examples

| Refs | Avg relevance | Old score | New score | Change |
|------|--------------|-----------|-----------|--------|
| 1 | 0.90 | 0.90 | 0.63 | −0.27 |
| 2 | 0.90 | 0.95 | 0.78 | −0.17 |
| 3 | 0.90 | 0.95 | 0.86 | −0.09 |
| 4 | 0.90 | 0.95 | 0.91 | −0.04 |
| 5 | 0.90 | 0.95 | 0.95 | 0.00 |
| 8 | 0.90 | 1.00 | 1.00 | 0.00 |
| 2 | 0.60 | 0.65 | 0.53 | −0.12 |
| 5 | 0.60 | 0.65 | 0.65 | 0.00 |

### Rationale

The penalty values were chosen to be:
- Meaningful: 2 refs now scores ~0.78 vs 0.95 (a real difference at this scale)
- Not destructive: 5+ refs at any relevance are not penalized
- Conservative: no change above 5 refs, no change to the relevance/diversity logic

This is the minimum justified change. The penalty multipliers are not derived from a dataset — they are principled approximations reflecting that evidence coverage increases logarithmically with count.

---

## Other Score Dimensions — No Change

### novelty_score

Current formula (text-length proxy) is acknowledged as imprecise. No calibration change in Phase 7C. The Phase 4B real embedding novelty gate is the real novelty check — the scoring formula is a secondary signal.

### plausibility_score, impact_score

These use text-length proxies. Not calibrated in Phase 7C. Would require a larger dataset of human-labeled examples to calibrate reliably.

### simulation_readiness_score

Binary at 0.9/1.0/0.3. No change.

### validation_cost_score

Tiered by testability_window_hours. No change.

---

## Impact on Existing Campaigns

Scores from Phase 7A/7B campaigns were computed with the old formula. They are **not retroactively recalculated** — that would break reproducibility. New campaigns from Phase 7C onward will use the calibrated formula.

For cross-campaign comparison: note the schema version in the evaluation pack.
