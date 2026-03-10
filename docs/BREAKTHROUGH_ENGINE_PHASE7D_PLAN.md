# Phase 7D Plan: Measurement Closure and Full-Fidelity Evaluation

**Branch**: `breakthrough-engine-phase7d-eval-profile`
**Based on**: `breakthrough-engine-phase7c-telemetry-calibration` @ `8ec8c36`
**Date**: 2026-03-09
**Status**: IN PROGRESS

---

## Objective

Close the last two known telemetry integrity failures from Phase 7C-B, create a true
evaluation-grade clean-energy campaign profile, collect a trustworthy 5-campaign reviewed
batch, and prepare the system for Bayesian policy optimization.

---

## Root Cause Analysis: Remaining Integrity Failures

### Failure 1: generated_count_mismatch

**Source**: `daily_search.py`, `run_campaign()`:
```python
result.total_candidates_generated = stage1_result.trials_attempted * max(
    program.candidate_budget, 1
)
```
This arithmetic estimate (trials × budget) diverges from actual DB row count when:
- The orchestrator generates fewer candidates than budget (quality gates, timeouts)
- Candidates are retried or deduplicated

**Fix**: In `_stage1_exploration()`, accumulate actual candidate count per trial from
`trial_repo.list_candidates_for_run(run_record.id)`. Store in `stage1_result.details["actual_candidates_generated"]`.
Use this in `run_campaign()` instead of the arithmetic estimate.

### Failure 2: falsification_missing

**Source**: `daily_search.py`, `_stage3_falsification()`:
```python
for candidate, score in shortlisted[:stage.max_trials]:
```
Only the top-K shortlisted candidates receive falsification. All other finalists get
`risk="MISSING"` in the evaluation pack.

**Fix**: Add `falsify_all_finalists: bool = False` to `LadderConfig`. When True, stage 3
falsifies ALL finalists (not just shortlisted). The evaluation profile sets this to True.

---

## Implementation Plan

### Priority 1: Integrity Fixes

1. `daily_search.py`:
   - `_run_single_trial()`: count ALL candidates for the run via `list_candidates_for_run`
   - `_stage1_exploration()`: accumulate counts, store in `details["actual_candidates_generated"]`
   - `run_campaign()`: use `stage1_result.details["actual_candidates_generated"]`
   - `LadderConfig`: add `falsify_all_finalists: bool = False`
   - `run_campaign()`: when `falsify_all_finalists=True`, pass `all_finalists` to stage 3

2. `campaign_manager.py`:
   - `CampaignProfile`: add `falsify_all_finalists: bool = False`
   - `load_campaign_profile()`: load from YAML
   - `_run_ladder_with_retries()`: pass `falsify_all_finalists` to `LadderConfig`

### Priority 2: Evaluation Profile

3. `config/campaign_profiles/eval_clean_energy_30m.yaml`:
   - `profile_type: evaluation`
   - `falsify_all_finalists: true`
   - `stage2_shortlist_size: 8` (large enough to pass all finalists to stage 3)
   - `stage3.max_trials: 10` (cover all finalists)
   - `falsification.strict_mode: true`
   - 30-minute wall clock budget

### Priority 3: Review Labels

4. `db.py`: Migration 10 — `bt_review_labels` table
5. CLI: `review-label add` command
6. Batch summary: include review labels in CSV export

### Priority 4: Evaluation Pack v003

7. `evaluation_pack.py`:
   - Schema version: v002 → v003 for evaluation-grade runs
   - For `profile_type == "evaluation"`: raise if integrity_ok is False
   - Export `review_labels` section in pack

### Priority 5: Batch Collection

8. Strict validation campaign (1 run, evaluation profile)
9. If validation passes: 5-campaign reviewed batch

---

## Acceptance Criteria

| Check | Criteria |
|-------|----------|
| generated_count_mismatch | Not present in any evaluation-grade pack |
| falsification_missing | Not present in any evaluation-grade pack |
| integrity_ok | True for all evaluation-grade campaigns |
| evaluation profile | eval_clean_energy_30m exists and is stable |
| review labels | Captured for champion and at least 1 runner-up per campaign |
| batch | 5 campaigns completed, all with integrity_ok=True |
| tests | All 581 + new Phase 7D tests pass |

---

## Non-Goals

- Do not merge to main
- Do not redesign the architecture
- Do not weaken novelty thresholds
- Do not add Omniverse
- Keep all tests offline-safe
- Preserve production embeddings
- Preserve one-publication-per-run invariant
