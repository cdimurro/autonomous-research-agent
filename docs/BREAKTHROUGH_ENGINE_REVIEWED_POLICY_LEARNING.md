# Reviewed Policy Learning

**Phase**: 8
**Branch**: `breakthrough-engine-phase8-reviewed-learning`
**Date**: 2026-03-09

---

## Overview

Reviewed policy learning is the process of updating the engine's champion policy using both:

1. **Telemetry signals** — campaign-level metrics (scores, block rates, falsification results)
2. **Human review signals** — structured review labels (approve/reject/defer + confidence scores)

This is not full RL. It is a bounded, auditable, reviewer-grounded update loop.

---

## Policy Promotion States

```
challenger
    │ (meets probation criteria)
    ▼
probationary_champion
    │ (passes benchmark + reviewed batch)
    ▼
champion
    │ (regression detected)
    ▼
rolled_back
```

### State Definitions

| State | Meaning |
|-------|---------|
| `challenger` | Registered but unproven policy |
| `probationary_champion` | Passed telemetry criteria, under observation |
| `champion` | Full champion — all criteria passed |
| `rolled_back` | Demoted due to regression; retained for audit |

---

## Promotion Criteria

### Stage 1: Challenger → Probationary Champion

All of the following must be met:

| Criterion | Threshold |
|-----------|-----------|
| Minimum trial samples | ≥ 5 per domain pair |
| Novelty pass rate | ≥ champion − 0.05 |
| Top candidate final score | ≥ champion − 0.03 |
| Falsification pass rate | ≥ champion − 0.05 |
| Operator burden proxy | ≤ champion + 0.05 |
| Draft quality proxy | ≥ champion − 0.03 |
| Telemetry integrity | No integrity failures |
| Falsification completeness | Must not worsen |

### Stage 2: Probationary Champion → Full Champion

All of the following must be met:

| Criterion | Requirement |
|-----------|-------------|
| Phase 5 benchmark regression | No metric regresses > 0.05 |
| Phase 7D reviewed baseline regression | No champion score regression > 0.05 |
| Probation runs survived | ≥ 3 additional runs without rollback trigger |
| Review-label outcomes (if available) | Equal or better approval rate |
| Reviewed posterior mean (if available) | ≥ champion − 0.03 on key metrics |

### Review-Signal Gate (New in Phase 8)

If reviewer labels are available for both challenger and champion trials:

| Review Metric | Threshold |
|---------------|-----------|
| Approval probability | ≥ champion − 0.05 |
| Mean novelty confidence | ≥ champion − 0.05 |
| Mean technical plausibility | ≥ champion − 0.05 |
| Reject probability | ≤ champion + 0.05 |

If labels are not available, the review-signal gate is skipped and a warning is logged.

---

## Rollback Triggers

Rollback is triggered automatically when:

| Condition | Action |
|-----------|--------|
| Phase 5 benchmark regression > 0.05 on any metric | Immediate rollback |
| Reviewed batch champion score mean drops > 0.05 vs Phase 7D baseline | Rollback |
| Telemetry integrity failure in two consecutive campaigns | Rollback |
| Review approval rate drops > 0.10 vs Phase 7D reviewed baseline | Rollback |

Rollback is always logged with reason and timestamp.

---

## Challenger Limits

- At most **2 challengers** registered at any time
- At most **1 challenger** trialed per 10-campaign batch
- Challenger surfaces allowed:
  - `generation_prompt_variant` (synthesis_focus, evidence_heavy)
  - `diversity_steering_variant` (aggressive, conservative)
  - `evidence_ranking_weights` (custom weight dicts)
  - `negative_memory_strategy` (strict, permissive)
  - `bridge_selection_policy` (fixed, random)

---

## Review-Weighted Bayesian Updates

### New Reviewed Metrics

| Metric | Type | Unit | Description |
|--------|------|------|-------------|
| `review_approval` | Binary (Beta) | label | P(approve) per labeled candidate |
| `review_novelty_confidence` | Continuous (Normal) | label | Mean reviewer novelty confidence |
| `review_technical_plausibility` | Continuous (Normal) | label | Mean reviewer technical plausibility |
| `review_commercialization_relevance` | Continuous (Normal) | label | Mean reviewer commercialization relevance |

### Prior Design

All reviewed metrics start with a weakly informative prior:
- `review_approval`: Beta(2, 2) — 50% prior with 4 pseudo-observations (not dominated by sparse labels)
- Continuous metrics: Normal(0.5, 0.25) — centered at neutral confidence

### Update Rule

For each `approve` label: update `review_approval` with success=True
For each `reject` label: update `review_approval` with success=False
For each `defer` label: no update to `review_approval` (uncertainty — skip)
For novelty/plausibility/relevance: update continuous posterior with the reported value

### Posterior Summary Example

```
review_approval:
  prior: Beta(2,2) → mean=0.500, n=4 (pseudo)
  posterior after 3 approvals, 1 reject: Beta(5,3) → mean=0.625
  95% CI: [0.351, 0.867]
  uncertainty: high (n=4 real observations)
  interpretation: slight positive signal from reviewer labels
```

---

## Audit Trail

Every promotion, rollback, and review-signal gate check is logged:
- `bt_policy_trials` — trial records with posterior_summary and benchmark_metrics
- `bt_policies` — policy state with `is_champion`, `is_probation`, `previous_champion_id`
- `bt_policy_promotion_log` — detailed promotion/rollback audit (new in Phase 8)

---

## How to Run a Reviewed Policy Trial

```bash
# 1. Register a challenger
python -m breakthrough_engine policy register \
    --name "synthesis_focus_v1" \
    --description "Synthesis-focused prompt variant" \
    --generation-prompt-variant synthesis_focus

# 2. Run a campaign with the challenger
python -m breakthrough_engine campaign run \
    --profile eval_clean_energy_30m \
    --policy synthesis_focus_v1

# 3. Add review labels for this campaign's champion
python -m breakthrough_engine review-label add \
    --campaign-id <id> --candidate-id <id> \
    --role champion --decision approve \
    --novelty-confidence 0.85 --technical-plausibility 0.80 \
    --commercialization-relevance 0.70

# 4. Check label completeness
python -m breakthrough_engine label-completeness check --batch <batch_id>

# 5. Attempt promotion
python -m breakthrough_engine policy promote-to-probation --policy-id <id>

# 6. After 3+ runs, attempt full champion promotion
python -m breakthrough_engine policy promote-to-champion --policy-id <id>
```
