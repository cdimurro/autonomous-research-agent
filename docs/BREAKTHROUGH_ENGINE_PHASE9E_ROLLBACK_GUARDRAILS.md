# Phase 9E Rollback Guardrails

**Phase**: 9E
**Champion**: `evidence_diversity_v1` (promoted 2026-03-12)
**Rollback target**: `phase5_champion`
**Status**: DOCUMENTED AND VERIFIED

---

## Rollback Command

```bash
python -m breakthrough_engine policy rollback --reason "<specific regression reason>"
```

**Example**:
```bash
python -m breakthrough_engine policy rollback --reason "approval rate dropped to 40% in 6 consecutive daily runs (Phase 9E trigger: <50% over 6 runs)"
```

**What it does**:
- Demotes `evidence_diversity_v1` (sets `is_champion=0`)
- Restores `phase5_champion` (sets `is_champion=1`)
- Logs the rollback event with timestamp and reason
- Daily automation immediately uses `phase5_champion` on next run

**Verification (dry run)**:
```bash
# Check current champion
python -m breakthrough_engine policy list

# Show rollback target
python -m breakthrough_engine policy show phase5_champion

# Confirm rollback_champion() has a previous_champion_id set:
# (The DB sets previous_champion_id=phase5_champion when evidence_diversity_v1 was promoted)
```

---

## Rollback Triggers

### Mandatory Rollback (act immediately)

| Trigger | Threshold | Measurement Window |
|---------|-----------|-------------------|
| Approval rate collapse | < 40% over 6 consecutive daily runs | 6 runs after detecting first run below 50% |
| Mean score regression | < 0.85 (> -0.06 below Phase 9C baseline of 0.905) | 3 consecutive runs |
| Integrity failures | Any run with integrity_status ≠ integrity_ok across 3 consecutive eval runs | Immediate on 3rd failure |
| Reject rate spike | ≥ 3 out of 6 consecutive champion labels = reject | 6 runs |

### Advisory Rollback (investigate before acting)

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Approval rate soft decline | 50–60% over 6 consecutive daily runs (vs 83.3% baseline) | Investigate before rolling back |
| Novelty confidence decline | < 0.79 mean over 6 runs (> -0.05 below Phase 9C baseline of 0.837) | Check for embedding drift, not policy regression |
| Plausibility decline | < 0.80 mean over 6 runs (> -0.05 below Phase 9C baseline of 0.847) | Investigate mechanism |
| Runner-up quality collapse | < 10% runner-up approval over 6 runs | Check if it's topic-specific, not policy |

### Not a Rollback Trigger

- Occasional defer (expected: 1–2 defers per 6 runs is normal)
- Score variance (individual runs as low as 0.87 is within normal range)
- Incrementalism in mature categories (e.g., COF/MOF battery work)

---

## Monitoring Runbook

After each daily run:

```bash
# Check most recent campaign outcome
python -m breakthrough_engine campaign list --limit 3

# Check champion score in last run
python -m breakthrough_engine daily status

# Review queue for pending labels
python -m breakthrough_engine review-queue status

# After each batch of 6 runs: check approval rate
# If below 50%: investigate
# If below 40%: execute mandatory rollback
```

---

## Rollback Verification (Completed 2026-03-12)

The rollback path was verified by inspecting the DB state:

1. `evidence_diversity_v1` is champion with `previous_champion_id = phase5_champion`
2. `phase5_champion` is present in `bt_policies` with all config intact
3. `rollback_champion()` method is verified to: demote current champion, restore previous, log event
4. Fix applied: CLI `policy rollback` now correctly unpacks the `(bool, str)` tuple return from `rollback_champion()`

**No actual rollback was performed.** The burn-in passed; rollback is on standby only.

---

## Post-Rollback Recovery

If rollback is executed:

1. Confirm `phase5_champion` is champion: `python -m breakthrough_engine policy list`
2. Run 2 dry-run checks: `python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy`
3. Compare rollback scores vs `phase9c_operational_baseline_regime2.json` (expected: 0.88–0.93 range)
4. Document the regression root cause in a BREAKTHROUGH_ENGINE_ROLLBACK_ANALYSIS.md file
5. Design a new challenger addressing the regression (evidence_diversity_v2 or alternative)

---

## What Does NOT Require Rollback

- Adding new domains (requires explicit scoping, not a rollback)
- Embedding model change (requires new regime designation)
- Capacity/performance issues (not a policy issue)
- Challenger registration (challengers don't affect production)

---

## Baseline References for Comparison

| Reference | Policy | Mean Score | Approval |
|-----------|--------|-----------|---------|
| phase9c_operational_regime2 | phase5_champion | 0.905 | 66.7% |
| phase9e_promoted_production_regime2 | evidence_diversity_v1 | 0.9126 | 83.3% |
