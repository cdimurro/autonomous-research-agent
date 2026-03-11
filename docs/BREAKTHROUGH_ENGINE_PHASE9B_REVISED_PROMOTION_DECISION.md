# Phase 9B-Revised Promotion Decision

**Champion**: `phase5_champion`
**Challenger**: `synthesis_focus_v1`
**Date**: 2026-03-10
**Embedding Regime**: Regime 2 (`qwen3-embedding:4b`, 2560d)
**Trial**: `phase9b_ab_trial`
**Status**: AWAITING BATCH EXECUTION

---

## CURRENT VERDICT: INSUFFICIENT_EVIDENCE

**Reason**: No Regime 2 campaigns have been run yet. The Phase 9B batch has not been executed.

This is the correct state. The prior Phase 8B trial (3+3 campaigns under Regime 1 with inert policy actuation) is **not used** for this decision because:
1. It used Regime 1 (`nomic-embed-text`, 768d) — embedding space is different
2. Policy actuation was incomplete in Phase 8B (generation_prompt_variant was inert)

**This document will be updated after the 6+6 batch completes and labels are collected.**

---

## Promotion Gate Checklist (Current State)

### Data Sufficiency Gates

| Gate | Threshold | Actual | Status |
|------|-----------|--------|--------|
| min_campaigns_per_arm (champion) | ≥ 6 | 0 | ❌ BLOCKING |
| min_campaigns_per_arm (challenger) | ≥ 6 | 0 | ❌ BLOCKING |
| min_review_labels | ≥ 24 | 0 | ❌ BLOCKING |
| all campaigns integrity_ok=True | 100% | N/A | ⏳ |
| all campaigns falsification_complete | 100% | N/A | ⏳ |
| embedding_regime matches baseline | regime_2 | regime_2 (pending) | ⏳ |

### Quality Gates (Challenger vs Champion)

| Gate | Threshold | Actual | Status |
|------|-----------|--------|--------|
| top_candidate_final_score delta | ≥ −0.03 | N/A | ⏳ |
| review_approval_rate delta | ≥ −0.05 | N/A | ⏳ |
| review_technical_plausibility delta | ≥ −0.05 (expected positive) | N/A | ⏳ |
| review_novelty_confidence delta | ≥ −0.05 | N/A | ⏳ |
| review_reject_rate delta | ≤ +0.05 | N/A | ⏳ |
| Posterior 90% CI excludes zero (key metrics) | Required | N/A | ⏳ |

---

## Regime Correctness Check

| Check | Required | Status |
|-------|----------|--------|
| Baseline for comparison | `phase9_new_embedding_reviewed` (Regime 2) | ⏳ Pending freeze |
| Campaigns run under qwen3-embedding:4b | Yes (all 12) | ⏳ Pending batch |
| No comparison against phase7d_reviewed or phase8_reviewed | Enforced | ✅ |

---

## Expected Challenger Behavior (Hypothesis)

Based on the policy design, the expected outcome after the batch is:

| Metric | Expected Direction | Confidence | Rationale |
|--------|-------------------|------------|-----------|
| review_technical_plausibility | **IMPROVE** | High | synthesis_focus prompt explicitly demands mechanism clarity and testability |
| review_approval_rate | IMPROVE slightly | Medium | Better-reasoned candidates may score better with reviewers |
| review_novelty_confidence | NEUTRAL or slight decline | Medium | Novelty weight −10%; prompt doesn't emphasize novelty |
| top_candidate_final_score | NEUTRAL | Medium | Scoring shift may cancel out; depends on LLM response to synthesis prompt |
| review_reject_rate | No change or improvement | Medium | Fewer vague/untestable candidates expected |

**Challenger hypothesis**: Instructing the LLM to emphasize mechanism plausibility + weighting plausibility/testability higher in scoring produces candidates that reviewers approve at higher rates, particularly on technical_plausibility.

---

## Promotion Decision Logic

After batch completion, the decision follows this logic:

### If all gates pass AND posterior shows clear improvement:
```
VERDICT: promotion_recommended
ACTION: python -m breakthrough_engine policy promote synthesis_focus_v1 \
  --reason "Phase 9B reviewed trial: technical_plausibility improved by X, \
            approval rate maintained, all integrity gates green"
```

### If challenger shows no improvement but no regression:
```
VERDICT: promotion_not_recommended
REASON: No measurable benefit over champion policy.
ACTION: Keep phase5_champion. Design synthesis_focus_v2 targeting specific weaknesses.
```

### If challenger shows regression on any gate:
```
VERDICT: promotion_not_recommended
REASON: Regression detected on [metric]. Challenger is NOT an improvement.
ACTION: python -m breakthrough_engine policy rollback \
  --reason "synthesis_focus_v1 regression in Phase 9B: [specific metric]"
```

### If evidence remains ambiguous (CI overlaps zero on key metrics):
```
VERDICT: insufficient_evidence
REASON: Posteriors do not show clear direction.
ACTION: Run additional campaigns (expand to 10+10) before re-assessment.
```

---

## Auto-Promotion Status

**AUTO-PROMOTION IS OFF AND REMAINS OFF.**

This is a manual decision. The operator must review:
1. `runtime/challenger_trials/phase9b_ab_trial/arm_summary.md`
2. `runtime/challenger_trials/phase9b_ab_trial/review_labels.csv`
3. `runtime/challenger_trials/phase9b_ab_trial/posterior_summary.md`

Then decide, and if promoting:
```bash
python -m breakthrough_engine policy promote synthesis_focus_v1 \
  --reason "Phase 9B reviewed trial: <specific finding>"
```

---

## Daily Automation During Trial

Production daily automation remains champion-only throughout:
```bash
# Production (champion arm only)
python -m breakthrough_engine daily run production_daily_clean_energy

# Evaluation (champion arm only)
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Dry run / health check
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
```

Challenger is NEVER used in production daily automation until after promotion is executed.

---

## Update Log

| Date | Event |
|------|-------|
| 2026-03-10 | Phase 9B document created. Regime boundary established. Verdict: INSUFFICIENT_EVIDENCE (no Regime 2 data). |
| TBD | Phase 9B batch complete. Verdict to be updated. |
| TBD | Review labels collected. Posteriors updated. Final verdict issued. |
