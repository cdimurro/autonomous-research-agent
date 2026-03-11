# Phase 9 Promotion Readiness Assessment

**Date**: 2026-03-10
**Champion**: phase5_champion
**Challenger under evaluation**: synthesis_focus_v1

---

## Current State

Phase 9 has implemented real policy actuation. The system is now ready for a meaningful reviewed A/B batch. However, **the extended batch has not yet been run** (requires production LLM availability).

The infrastructure for assessment is in place; the evidence is pending.

---

## What Needs to Happen Before Promotion Can Be Assessed

1. Run 6+ champion arm campaigns with integrity_ok=True
2. Run 6+ challenger arm campaigns (with synthesis_focus prompt + weights) with integrity_ok=True
3. Collect at least 12 review labels (champion + runner-up per campaign)
4. Run `python -m breakthrough_engine challenger-trial build` to aggregate
5. Run `python -m breakthrough_engine challenger-trial compare` to assess

---

## Promotion Gate Checklist

### Telemetry Gates (all must be green)

| Gate | Threshold | Status |
|------|-----------|--------|
| min_campaigns_per_arm | ≥ 6 | PENDING — need extended batch |
| min_review_labels | ≥ 12 | PENDING |
| integrity_ok_rate (challenger) | 100% | PENDING |
| top_candidate_final_score delta | ≥ -0.03 | PENDING |
| novelty_pass_rate delta | ≥ -0.05 | PENDING |
| falsification_pass_rate delta | ≥ -0.05 | PENDING |
| operator_burden_proxy delta | ≤ +0.05 | PENDING |

### Review-Signal Gates (all must be green)

| Gate | Threshold | Status |
|------|-----------|--------|
| review_approval_rate delta | ≥ -0.05 | PENDING |
| review_technical_plausibility delta | ≥ -0.05 | PENDING (expected: positive) |
| review_novelty_confidence delta | ≥ -0.05 | PENDING |
| review_reject_rate delta | ≤ +0.05 | PENDING |

### Regression Checks

| Check | Threshold | Status |
|-------|-----------|--------|
| No metric below regression_threshold (0.05) | All clear | PENDING |
| Posterior credible interval excludes zero (for key metrics) | Required | PENDING |
| Phase 8 baseline maintained | champion_score ≥ 0.91192 - 0.03 | PENDING |

---

## Current Promotion Recommendation

**INSUFFICIENT_EVIDENCE**

Reason:
- Phase 8B trial: 3 champion + 3 challenger campaigns = insufficient (minimum 6 per arm)
- Phase 8B trial used inert policy (generation_prompt_variant was not wired)
- Phase 9 actuation is now complete but no new campaigns have been run yet
- No extended batch data exists

**No promotion, no rejection — simply insufficient data under real actuation conditions.**

---

## Expected Challenger Behavior After Actuation

Based on the policy design:

| Metric | Expected Direction | Confidence |
|--------|-------------------|------------|
| review_technical_plausibility | IMPROVE | High — synthesis_focus prompt explicitly demands mechanism clarity |
| review_approval_rate | IMPROVE slightly | Medium — more rigorous candidates may score better with reviewers |
| review_novelty_confidence | NEUTRAL or DECLINE | Medium — novelty weight -10%, prompt doesn't emphasize novelty |
| top_candidate_final_score | NEUTRAL | Medium — synthesis_focus candidates may score higher on plausibility |
| operator_burden_proxy | NEUTRAL | Low — similar review effort expected |

---

## Rollback Plan

If challenger shows regression after extended batch:
```bash
python -m breakthrough_engine policy rollback --reason "synthesis_focus_v1 regression in Phase 9 extended batch"
```

This immediately reverts to the previous champion. The daily automation will revert to standard prompt on next run.

---

## Phase 10 Readiness

If the extended batch shows clear evidence of improvement:
- Promote challenger to probationary champion
- Run 3 probationary production campaigns
- Collect review labels for probationary campaigns
- If no regression: promote to full champion

If not recommended:
- Keep phase5_champion
- Log lessons learned
- Design synthesis_focus_v2 based on identified weaknesses

---

## How to Run the Extended Batch

```bash
# Step 1: Champion arm (6 campaigns)
for i in 1 2 3 4 5 6; do
  python -m breakthrough_engine ds run eval_clean_energy_30m
done

# Step 2: Challenger arm (6 campaigns)
for i in 1 2 3 4 5 6; do
  python -m breakthrough_engine ds run eval_clean_energy_30m --policy synthesis_focus_v1
done

# Step 3: Add review labels (manual)
# For each campaign: champion + runner-up
python -m breakthrough_engine review-label add --campaign-id <id> --candidate-id <id> --decision approve

# Step 4: Build trial
python -m breakthrough_engine challenger-trial build \
  --champion-campaigns <c1,c2,c3,c4,c5,c6> \
  --challenger-id synthesis_focus_v1

# Step 5: Compare
python -m breakthrough_engine challenger-trial compare --trial-id <id>

# Step 6: If promoted:
python -m breakthrough_engine policy promote synthesis_focus_v1 --reason "Phase 9 reviewed trial: <specific reason>"
```
