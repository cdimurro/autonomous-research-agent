# Phase 8B: First Challenger Trial

**Phase**: 8B
**Challenger**: `synthesis_focus_v1` (id: ba0cb255c20f4995)
**Champion**: `phase5_champion`
**Date**: 2026-03-10
**Status**: IN PROGRESS (campaigns running)

---

## Challenger Definition

### synthesis_focus_v1

| Field | Value |
|-------|-------|
| Name | synthesis_focus_v1 |
| ID | ba0cb255c20f4995 |
| Version | 1.0 |
| Generation variant | synthesis_focus |
| Diversity variant | standard |
| Negative memory | standard |

**Single-surface scoring weight change** vs champion:

| Weight | Champion | Challenger | Change |
|--------|----------|------------|--------|
| novelty | 0.20 | 0.18 | -10% |
| plausibility | 0.20 | **0.25** | **+25%** |
| impact | 0.20 | 0.20 | unchanged |
| evidence_strength | 0.20 | 0.20 | unchanged |
| simulation_readiness | 0.10 | **0.12** | **+20%** |
| inverse_validation_cost | 0.10 | 0.05 | -50% |

**Hypothesis**: Candidates with higher plausibility and simulation_readiness scores will receive better reviewer approval rates and technical plausibility scores, indicating more actionable research leads.

**Rollback trigger**: Champion score mean regression > 0.05 vs Phase 8 reviewed baseline (0.91192).

---

## Trial Design

| Setting | Value |
|---------|-------|
| Profile | eval_clean_energy_30m |
| Total campaigns | 6 (3 champion + 3 challenger) |
| Champion arm | 3 campaigns from Phase 8 batch + new run |
| Challenger arm | 3 new campaigns |
| Integrity required | yes (eval grade) |
| Review labels | champion + runner-up per campaign |
| Minimum evidence | 2 campaigns per arm |

---

## Implementation Notes

> **Important**: The current `CampaignManager` does not inject scoring weights from the policy config into the campaign execution pipeline. The scoring weight difference between champion and challenger is **registered in the policy record** and available for future prompt injection (Phase 9 capability), but the actual generated candidates in this trial are produced by the same underlying scoring logic.
>
> This trial therefore primarily validates the **comparison infrastructure** and establishes baseline metrics for future trials when prompt injection is implemented.
>
> The trial is still valuable: it establishes the full artifact pipeline, verifies that comparison works end-to-end, and produces real reviewed evidence for both arms.

---

## Promotion Gate Requirements

For challenger → probationary champion, all must be met:

| Gate | Requirement |
|------|-------------|
| Telemetry: champion_score_mean | ≥ champion - 0.03 |
| Telemetry: block_rate | ≤ champion + 0.10 |
| Telemetry: integrity_ok_rate | = 1.00 |
| Review signal: approval_rate | ≥ champion - 0.05 |
| Review signal: novelty_confidence | ≥ champion - 0.05 |
| Review signal: technical_plausibility | ≥ champion - 0.05 |
| Baseline regression guard | challenger mean ≥ phase8_reviewed mean - 0.05 |

**Automatic promotion is OFF.** The `compare_arms()` function returns an assessment only; promotion requires explicit operator action:

```bash
# Only if promotion is recommended:
python -m breakthrough_engine policy promote ba0cb255c20f4995 \
  --reason "Challenger passed review-signal gate after 6-campaign trial"
```

---

## Trial Artifacts

After the trial completes:

| Artifact | Location |
|----------|----------|
| Per-campaign CSV | `runtime/challenger_trials/phase8b_trial_20260310/policy_trials.csv` |
| Summary JSON | `runtime/challenger_trials/phase8b_trial_20260310/challenger_vs_champion_summary.json` |
| Summary MD | `runtime/challenger_trials/phase8b_trial_20260310/challenger_vs_champion_summary.md` |

---

## CLI Commands

```bash
# Build trial summary after campaigns are run
python -m breakthrough_engine challenger-trial build \
  --champion-campaigns <c1> <c2> <c3> \
  --challenger-campaigns <c4> <c5> <c6> \
  --challenger-id ba0cb255c20f4995 \
  --output-dir runtime/challenger_trials/phase8b_trial_20260310 \
  --profile eval_clean_energy_30m \
  --baseline phase8_reviewed

# Show existing trial
python -m breakthrough_engine challenger-trial show \
  runtime/challenger_trials/phase8b_trial_20260310
```

---

## Evidence Required for Future Promotion

Before promoting synthesis_focus_v1, collect:

1. ≥ 6 campaigns per arm (currently 3 per arm — insufficient)
2. Review labels for all champions and runner-ups in both arms
3. Compare reviewer approval rates between arms
4. Verify no score regression vs Phase 8 reviewed baseline
5. Run Phase 5 algorithmic regression check

Even if all gates pass, the operator must manually execute:
```bash
python -m breakthrough_engine policy promote ba0cb255c20f4995
```
