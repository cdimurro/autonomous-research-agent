# Phase 8B Plan: Reviewed Learning Loop Completion

**Branch**: `breakthrough-engine-phase8b-reviewed-loop`
**Base branch**: `breakthrough-engine-phase8-reviewed-learning` (commit `0f92f11`)
**Date**: 2026-03-10
**Status**: IN PROGRESS

---

## Objective

Close the first full reviewed-learning loop:
1. Complete 20 pending review labels on the Phase 8 batch
2. Convert labels into Bayesian posterior signals
3. Freeze Phase 8 as a new trusted reviewed baseline
4. Register `synthesis_focus_v1` as the first challenger
5. Run a bounded 6-campaign challenger-vs-champion comparison
6. Keep promotion manual; document the evidence
7. Launch bounded daily automation with the current champion

---

## Starting State

| Field | Value |
|-------|-------|
| Base branch | breakthrough-engine-phase8-reviewed-learning |
| Base commit | 0f92f11 |
| Tests | 695 passing, 0 failures |
| DB migrations | 11 |
| Schema version | v003 (eval), v002 (smoke/pilot) |
| Phase 5 baseline | frozen @ runtime/baselines/phase5_validated_benchmark.json |
| Phase 7D baseline | frozen @ runtime/baselines/phase7d_reviewed_baseline.json |
| Phase 8 batch | phase8_batch_20260309 — 10 campaigns, mean=0.91192 |
| Phase 8 labels | 0 / 20 collected |
| Champion policy | phase5_champion |
| Challengers | 0 registered |
| Daily automation | profiles ready, not yet launched |

---

## Deliverable Plan

| Deliverable | Status | Notes |
|-------------|--------|-------|
| A. Review-label completion (20 labels) | PENDING | |
| B. Phase 8 reviewed baseline freeze | PENDING | |
| C. synthesis_focus_v1 challenger registration | PENDING | |
| D. Bounded 6-campaign challenger-vs-champion trial | PENDING | |
| E. Manual promotion guardrails | PENDING | |
| F. Bounded daily automation launch | PENDING | |
| G. Runtime artifact backup/manifest | PENDING | |
| H. Tests | PENDING | |

---

## Implementation Order

1. Infrastructure additions (policy register CLI, baseline freeze CLI, challenger_trial.py)
2. Execute Phase 8B labeling (all 20 labels)
3. Freeze Phase 8 baseline
4. Register synthesis_focus_v1 challenger
5. Run 6-campaign trial (3 champion + 3 challenger)
6. Dry-run daily automation, document launch commands
7. Tests + docs + commit

---

## Key Design Decisions

### synthesis_focus_v1 Design
- Single configurable surface change: `scoring_weights` gives +10% weight to `synthesis_feasibility`
- `generation_prompt_variant = "synthesis_focus"` (future prompt injection hook)
- All other parameters identical to champion
- Hypothesis: synthesis-emphasis candidates produce more actionable research leads
- Rollback safety: champion remains unchanged; any score drop auto-triggers rollback

### Review Label Judgment Criteria
- **approve**: high novelty, technically grounded, commercially relevant
- **reject**: known prior art, technically implausible, or commercially misaligned
- **defer**: moderate interest, uncertainty on key dimension

### Challenger Trial Design
- 6 campaigns total: 3 champion + 3 challenger
- All with `eval_clean_energy_30m` profile (integrity required)
- Minimum evidence for promotion recommendation: all 6 campaigns + 6 champion + 6 runner-up labels
- Promotion decision: explicit manual only

### Daily Automation Launch
- Start with dry-run validation
- Use current champion policy only
- Challenger stays out of production automation

---

## Constraints Reminder

1. No merge to main
2. No architecture redesign
3. Automatic promotion OFF
4. Max 1 challenger (synthesis_focus_v1 only)
5. All tests offline-safe
6. No Omniverse
7. No large dashboard
