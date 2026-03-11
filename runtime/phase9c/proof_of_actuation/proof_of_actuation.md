# evidence_diversity_v1 — Proof of Actuation

**Policy**: evidence_diversity_v1
**Surface**: evidence_ranking_weights
**Method**: Deterministic ranking comparison on controlled 3-item evidence set
**Result**: ACTUATION VERIFIED — ranking order changes under challenger weights

---

## Controlled Evidence Set

| Item | api_relevance | mechanism_overlap | domain_overlap | Description |
|------|--------------|-------------------|----------------|-------------|
| ev_A | 0.90 (high) | 0.20 (low) | 0.50 | High API relevance, low mechanism fit |
| ev_B | 0.40 (low) | 0.80 (high) | 0.50 | Low API relevance, strong mechanism fit |
| ev_C | 0.60 (med) | 0.50 (med) | 0.50 | Medium across both |

---

## Champion Policy Weights vs Challenger Weights

| Weight | Champion | Challenger |
|--------|----------|-----------|
| api_relevance | 0.35 | 0.20 |
| domain_overlap | 0.30 | 0.30 |
| mechanism_overlap | 0.20 | 0.35 |
| baseline | 0.15 | 0.15 |

---

## Ranking Comparison

| Policy | ev_A score | ev_B score | ev_C score | Ranked order |
|--------|-----------|-----------|-----------|-------------|
| Champion | **0.580** | 0.525 | 0.535 | **A** > C > B |
| Challenger | 0.475 | **0.585** | 0.520 | **B** > C > A |

**Top item flipped**: Champion selects ev_A (high API relevance); Challenger selects ev_B (high mechanism overlap).

---

## Interpretation

The challenger policy is **not inert**. The evidence_ranking_weights change produces a meaningfully different ranked evidence set:

- The champion policy surfaces the most API-popular papers regardless of mechanism fit
- The challenger policy surfaces the most mechanism-relevant papers, which may be less highly ranked by external APIs

This changes what evidence the candidate generator receives, which is the intended mechanism of action for evidence_diversity_v1.

---

## What This Does Not Prove

This is a structural proof only. It confirms the pipeline wiring is correct. It does **not** predict the A/B trial outcome — that requires 6+6 campaigns with review labels.
