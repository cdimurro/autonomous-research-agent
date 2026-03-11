# Phase 9 A/B Trial Framework

**Date**: 2026-03-10
**Champion**: phase5_champion
**Challenger**: synthesis_focus_v1

---

## Phase 8B Trial Result (Historical)

The Phase 8B trial ran 3 champion + 3 challenger campaigns = 6 total.
- Result: `insufficient_evidence`
- Key reason: policy actuation was NOT complete — scoring weights differed on paper but generation_prompt_variant was inert.
- Champion mean score: 0.92387 | Challenger mean score: 0.92021 | Delta: -0.00367

**This trial was primarily an infrastructure validation, not a real behavioral test.**

---

## Phase 9 Trial Design

Now that policy actuation is real, A/B trials test genuine behavioral differences:

### Arm A: Champion (phase5_champion)
- System prompt: `standard` (baseline hypothesis generation rules)
- Scoring: default weights (novelty=0.20, plausibility=0.20, ...)
- Evidence ranking: default weights

### Arm B: Challenger (synthesis_focus_v1)
- System prompt: `synthesis_focus` (mechanism-first, testability emphasis, plausibility gate)
- Scoring: plausibility=0.25 (+25%), simulation_readiness=0.12 (+20%), novelty=0.18 (-10%), inverse_validation_cost=0.05 (-50%)
- Evidence ranking: default (no override)

### Trial Protocol
- Profile: `eval_clean_energy_30m` (evaluation-grade, integrity gating required)
- Campaigns per arm: 6 minimum (12 total) for Phase 9 extended batch
- Integrity requirement: `integrity_ok=True` for all campaigns
- Review labels required: champion + runner-up for each campaign
- Arm assignment: explicit via `--policy` flag

### Success Criteria
- At least 6 campaigns per arm completed with integrity_ok
- At least 12 review labels collected (champion + runner-up per campaign)
- Bayesian posterior shows clear direction (not flat)
- Promotion readiness verdict: one of {promotion_recommended, promotion_not_recommended, insufficient_evidence}

---

## Trial Commands

```bash
# Run champion arm campaign
python -m breakthrough_engine ds run eval_clean_energy_30m

# Run challenger arm campaign
python -m breakthrough_engine ds run eval_clean_energy_30m --policy synthesis_focus_v1

# After 6+ per arm, build trial comparison
python -m breakthrough_engine challenger-trial build \
  --champion-campaigns <id1,id2,id3,id4,id5,id6> \
  --challenger-id synthesis_focus_v1

# Export trial artifacts
python -m breakthrough_engine challenger-trial export --trial-id <id>
```

---

## Promotion Readiness Thresholds

Promotion from challenger → probation requires ALL of:

| Metric | Required | Notes |
|--------|----------|-------|
| review_approval_rate | challenger >= champion - 0.05 | No significant regression |
| review_novelty_confidence | challenger >= champion - 0.05 | Novelty not degraded |
| review_technical_plausibility | challenger >= champion - 0.05 | Should improve for synthesis_focus |
| review_reject_rate | challenger <= champion + 0.05 | Not more rejections |
| top_candidate_final_score | challenger >= champion - 0.03 | Score regression guard |
| integrity_ok_rate | 100% | All campaigns must pass |
| min_campaigns_per_arm | 6 | Statistical basis |
| min_review_labels | 12 | Label sufficiency |

### Expected Challenger Advantage
- `review_technical_plausibility` should improve (synthesis_focus emphasizes mechanism)
- `review_approval_rate` may improve (better-reasoned candidates)

### Potential Challenger Weakness
- `review_novelty_confidence` may decline (synthesis_focus deemphasizes novelty)
- `top_candidate_final_score` may decline slightly (scoring weight shift)

---

## Insufficient Evidence Conditions

Trial remains `insufficient_evidence` if:
- Fewer than 6 campaigns completed per arm
- Fewer than 12 review labels collected
- Posterior uncertainty (credible interval) overlaps zero for key metrics
- Too few campaigns to distinguish from sampling noise

---

## Artifacts to Export After Batch

| Artifact | Path | Description |
|----------|------|-------------|
| arm_summary.json | runtime/challenger_trials/<trial_id>/ | Per-arm aggregate metrics |
| arm_summary.md | runtime/challenger_trials/<trial_id>/ | Human-readable summary |
| policy_trials.csv | runtime/challenger_trials/<trial_id>/ | Per-campaign metrics |
| review_labels.csv | runtime/challenger_trials/<trial_id>/ | All review labels used |
| champions.csv | runtime/challenger_trials/<trial_id>/ | Champion candidates per campaign |
| finalists_combined.csv | runtime/challenger_trials/<trial_id>/ | All finalists |
| campaign_metrics.csv | runtime/challenger_trials/<trial_id>/ | Per-campaign pipeline metrics |

---

## Promotion Decision (Manual)

After the trial, the operator reviews:
1. `arm_summary.md` — high-level comparison
2. `review_labels.csv` — individual label outcomes
3. Posterior summaries — Bayesian update direction
4. Regression checks — no metric below threshold

Then manually runs (if promotion is warranted):
```bash
python -m breakthrough_engine policy promote synthesis_focus_v1 --reason "Phase 9 reviewed trial: plausibility improvement confirmed, no regression"
```

**Automatic promotion is OFF. This step is always manual.**
