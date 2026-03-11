# Phase 9B Promotion Decision

**Date:** 2026-03-10  
**Branch:** breakthrough-engine-phase9-policy-actuation  
**Trial:** phase9b_ab_trial  
**Verdict:** PROMOTION_NOT_RECOMMENDED  

---

## Summary

After completing a 6+6 Regime 2 A/B batch and collecting 24 structured review labels (12 per arm), the synthesis_focus_v1 challenger policy is **not recommended for promotion** to champion.

**Champion remains: phase5_champion**  
**Automation: Champion-only (unchanged)**

---

## Evidence

### Score Results (Regime 2 baseline: 0.89737)

| Arm | Policy | Campaigns | Mean Score | vs Baseline |
|-----|--------|-----------|------------|-------------|
| Champion | phase5_champion | 6 | **0.90804** | +0.011 |
| Challenger | synthesis_focus_v1 | 6 | 0.87789 | −0.019 |

Score delta: −0.0302 (threshold ≥ −0.03 → FAIL by 0.0002)

### Review Labels (24 labels: 12 per arm)

| Metric | Champion | Challenger | Delta |
|--------|----------|------------|-------|
| Approval rate | **75.0%** (9/12) | 25.0% (3/12) | −50.0 pp |
| Non-reject rate | **100%** (0 rejects) | 83.3% (2 rejects) | −16.7 pp |
| Beta posterior mean | 0.688 | 0.312 | −0.376 |

### Dimension Posteriors

| Dimension | Champion | Challenger | Delta |
|-----------|----------|------------|-------|
| Novelty confidence | 0.783 ± 0.041 | 0.713 ± 0.066 | −0.070 |
| Technical plausibility | 0.763 ± 0.050 | 0.694 ± 0.066 | −0.069 |
| Commercialization relevance | 0.710 ± 0.052 | 0.633 ± 0.076 | −0.077 |

### Block Rate

Both arms: 0.0% (same embedding regime — no block rate signal)

---

## Gate Assessment

| Gate | Threshold | Champion | Challenger | Pass? |
|------|-----------|----------|------------|-------|
| Score delta | ≥ −0.03 | — | −0.0302 | ❌ FAIL |
| Approval rate | challenger ≥ champion | 75% | 25% | ❌ FAIL |
| Non-reject rate | challenger ≥ 80% | 100% | 83.3% | ✅ PASS |
| Novelty confidence | delta ≥ 0 | 0.783 | 0.713 | ❌ FAIL |
| Technical plausibility | delta ≥ 0 | 0.763 | 0.694 | ❌ FAIL |

**4 of 5 gates fail. Verdict: PROMOTION_NOT_RECOMMENDED.**

---

## Interpretation

The synthesis_focus_v1 challenger was configured with:
- `synthesis_focus` prompt variant (vs `standard`)
- Plausibility weight +25%, sim_readiness weight +20%
- Novelty weight −10%, inverse_validation_cost weight −50%

The weight adjustments appear to have **over-corrected**: boosting plausibility at the expense of novelty and overall candidate quality. The champion's score advantage is consistent across all 6 campaigns, and the label signal is emphatic — champion approval 75% vs challenger 25%.

The one near-pass (score delta just 0.0002 below threshold) does not override the cumulative label regression.

---

## Action Items

1. **No promotion.** Champion remains phase5_champion.
2. **Automation unchanged.** Daily automation runs champion-only.
3. **Retire synthesis_focus_v1** as active challenger for this regime.
4. **Future challenger design:** Consider reducing the plausibility over-weighting. A smaller shift (e.g., +10% instead of +25%) might improve synthesis without degrading novelty.
5. **Next trial:** Design a new challenger that addresses novelty deficit while maintaining plausibility gains.

---

## Artifacts

| Artifact | Path |
|----------|------|
| Trial summary JSON | runtime/challenger_trials/phase9b_ab_trial/challenger_vs_champion_summary.json |
| Trial summary MD | runtime/challenger_trials/phase9b_ab_trial/challenger_vs_champion_summary.md |
| Posterior summary JSON | runtime/challenger_trials/phase9b_ab_trial/posterior_summary.json |
| Posterior summary MD | runtime/challenger_trials/phase9b_ab_trial/posterior_summary.md |
| Review labels CSV | runtime/challenger_trials/phase9b_ab_trial/review_labels.csv |
| Regime 2 baseline | runtime/baselines/phase9_new_embedding_reviewed.json |

---

## Regime Note

All 12 A/B campaigns and the 5-campaign Regime 2 baseline were run under:
- Embedding model: qwen3-embedding:4b (2560d)
- Embedding regime: regime_2
- Commit: bbd7692 (Phase 9)

Results are NOT comparable to Regime 1 baselines (nomic-embed-text, 768d, commits ≤ 1b52a0f).
