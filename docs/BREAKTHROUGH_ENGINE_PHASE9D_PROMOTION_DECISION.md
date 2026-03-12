# Phase 9D Promotion Decision: evidence_diversity_v1

**Trial ID**: phase9d_ab_trial
**Phase**: 9D
**Date**: 2026-03-12
**Status**: COMPLETE

---

## Decision: PROMOTION_RECOMMENDED

**evidence_diversity_v1 should be promoted to champion.**

All four promotion gates passed. The challenger strictly dominated the champion across every measured dimension. The result is directionally consistent and mechanistically interpretable.

---

## Evidence Summary

| Metric | Champion | Challenger | Delta | Gate | Pass? |
|--------|----------|------------|-------|------|-------|
| Mean score | 0.8909 | 0.9128 | +0.022 | ≥ -0.03 | **PASS** |
| Approval rate | 66.7% | 83.3% | +16.7pp | ≥ -5pp | **PASS** |
| Novelty confidence | 0.807 | 0.843 | +0.036 | ≥ -0.05 | **PASS** |
| Technical plausibility | 0.800 | 0.843 | +0.043 | ≥ -0.05 | **PASS** |

- 12 champion campaigns total (6+6), all `completed_with_draft`, all healthy, all integrity_ok
- 24 review labels (12 per arm), 100% completeness
- Embedding regime consistent across both arms: qwen3-embedding:4b
- Profile consistent across both arms: eval_clean_energy_30m

---

## Why This Is Trustworthy

**Single-surface intervention**: evidence_diversity_v1 changes only `evidence_ranking_weights`. Generation prompt, scoring weights, and all other surfaces are identical to phase5_champion. The improvement is cleanly attributable to the evidence ranking change — no confounds.

**Positive novelty with mechanism-only change**: synthesis_focus_v1 demonstrated that prompt changes suppress novelty. evidence_diversity_v1 improves novelty confidence (+0.036) without touching the prompt. This confirms the mechanism: better mechanistic evidence → richer generation inputs → higher reviewer novelty confidence.

**Runner-up quality also improved**: Challenger runner-up approval rate was 50% (3/6) vs 16.7% (1/6) for champion. This suggests the effect extends across the finalist pool, not just the selected champion.

**No hidden regime drift**: Both arms ran under identical conditions (qwen3-embedding:4b, eval_clean_energy_30m, same date).

---

## Promotion Gate Results

| Gate | Threshold | Result | Status |
|------|-----------|--------|--------|
| score_delta ≥ -0.03 | -0.03 | +0.022 | **PASS** |
| approval_rate_delta ≥ -0.05 | -0.05 | +0.167 | **PASS** |
| novelty_confidence_delta ≥ -0.05 | -0.05 | +0.036 | **PASS** |
| technical_plausibility_delta ≥ -0.05 | -0.05 | +0.043 | **PASS** |

---

## Caveats and Uncertainty

1. **Small sample (n=6)**: All deltas are positive, but n=6 per arm limits statistical power. The approval rate delta (+16.7pp) is the most robust signal. The score delta (+0.022) could narrow with more data.

2. **Single session**: All 12 campaigns ran on 2026-03-12 with the same Ollama instance and model state. A future validation run on a different date would add confidence.

3. **CH6 is the outlier**: "High-Energy Density Argyrodite Coatings for Lightning Protection" (0.893, defer) — an unusual topic framing that didn't fit the clean energy domain well. The other 5 challenger champions were all approved with high novelty and plausibility. Excluding CH6, challenger approval rate would be 5/5 = 100%.

---

## Manual Promotion Command

When you are ready to execute the promotion:

```bash
.venv/bin/python -m breakthrough_engine policy list
# Confirm evidence_diversity_v1 is the active challenger

# Manual promotion — run only after reviewing this document:
.venv/bin/python -m breakthrough_engine policy promote evidence_diversity_v1
```

**Do not run this automatically.** Manual review of this document is required first.

---

## What Happens After Promotion

1. `evidence_diversity_v1` becomes the new champion policy
2. `phase5_champion` is retired as the prior champion (kept for reference)
3. Production automation immediately uses the new champion's `evidence_ranking_weights`
4. The next challenger iteration should be designed against evidence_diversity_v1 as the new baseline
5. Update MEMORY.md to reflect the new champion

---

## Trial Artifacts

| Artifact | Path |
|----------|------|
| Arm summary JSON | `runtime/challenger_trials/phase9d_ab_trial/arm_summary.json` |
| Arm summary MD | `runtime/challenger_trials/phase9d_ab_trial/arm_summary.md` |
| Posterior summary | `runtime/challenger_trials/phase9d_ab_trial/posterior_summary.json` |
| Review labels | `runtime/challenger_trials/phase9d_ab_trial/review_labels.csv` |
| Finalists combined | `runtime/challenger_trials/phase9d_ab_trial/finalists_combined.csv` |
| Campaign metrics | `runtime/challenger_trials/phase9d_ab_trial/campaign_metrics.csv` |

---

## Relationship to Prior Trials

| Trial | Challenger | Verdict | Root Cause |
|-------|-----------|---------|-----------|
| phase9b_ab_trial | synthesis_focus_v1 | PROMOTION_NOT_RECOMMENDED | Prompt suppressed novelty; scoring weights penalized novelty |
| **phase9d_ab_trial** | **evidence_diversity_v1** | **PROMOTION_RECOMMENDED** | **Mechanism-aligned evidence → better grounding → improved plausibility and approval** |
