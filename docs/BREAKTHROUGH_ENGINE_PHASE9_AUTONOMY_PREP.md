# Phase 9 Autonomous Operation Preparation

**Date**: 2026-03-10
**Champion**: phase5_champion (production only)
**Challenger**: synthesis_focus_v1 (evaluation/trial only)

---

## Design Principle

Autonomous daily operation uses the current champion exclusively.
The challenger is excluded from production automation.
All autonomous runs are bounded (1 per profile per day).
Review queue insertion is mandatory for all production runs.

---

## Daily Automation Profiles

### Evaluation Profile (evaluation_daily_clean_energy)

```yaml
profile_name: evaluation_daily_clean_energy
profile_type: evaluation_daily
campaign_profile: eval_clean_energy_30m
domain: clean-energy
max_runs_per_day: 1
require_integrity_ok: true
require_falsification_complete: true
export_evaluation_pack: true
insert_review_queue: true
review_labels_required:
  champion: true
  runner_up: true
log_posterior_snapshot: true
```

**Policy used**: Champion only (phase5_champion)
**Purpose**: Evaluation-grade campaign for quality monitoring and Bayesian learning
**Command**: `python -m breakthrough_engine daily run evaluation_daily_clean_energy`

### Production Profile (production_daily_clean_energy)

```yaml
profile_name: production_daily_clean_energy
profile_type: production_daily
campaign_profile: overnight_clean_energy
domain: clean-energy
max_runs_per_day: 1
require_integrity_ok: false
export_evaluation_pack: false
insert_review_queue: true
review_labels_required:
  champion: false
```

**Policy used**: Champion only (phase5_champion)
**Purpose**: Best-effort overnight publication
**Command**: `python -m breakthrough_engine daily run production_daily_clean_energy`

---

## Safe Launch Runbook

### Before any autonomous run:
1. **Health check**: `python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy`
2. **Verify champion**: `python -m breakthrough_engine policy list` → confirm phase5_champion is champion
3. **Check review queue**: `python -m breakthrough_engine review-queue status` → not overloaded
4. **Verify embeddings**: `python -m breakthrough_engine preflight check`

### Launch evaluation campaign:
```bash
python -m breakthrough_engine daily run evaluation_daily_clean_energy
```

### Launch production campaign:
```bash
python -m breakthrough_engine daily run production_daily_clean_energy
```

### Morning-after inspection:
```bash
# Check what ran
python -m breakthrough_engine daily status

# Check campaign outcome
python -m breakthrough_engine campaign list --limit 5

# Check review queue for new items
python -m breakthrough_engine review-queue status

# Check posterior state
python -m breakthrough_engine policy show phase5_champion
```

---

## Challenger Exclusion from Production

**Challengers are never used in daily automation.** The automation always fetches the current champion from the policy registry.

If a challenger is accidentally promoted to champion while Phase 9 trials are ongoing, the production automation will use it. To prevent this:
- Keep automatic promotion OFF (enforced in code)
- Never manually promote during an ongoing trial
- Check `python -m breakthrough_engine policy list` before each production run

---

## Evidence Accumulation

Each autonomous run contributes to the evidence base:
- **Policy snapshot** logged at run start (which policy, which settings)
- **Review queue item** inserted (for operator labeling)
- **Posterior snapshot** logged if evaluation profile
- **Artifact manifest** updated

Over time, this accumulates reviewed evidence for future policy comparison.

---

## Rollback Commands

If something goes wrong:
```bash
# Roll back champion (reverts to previous)
python -m breakthrough_engine policy rollback --reason "regression detected in autonomous run"

# Stop any running campaign (signal-safe)
# SIGTERM is handled gracefully by campaign_manager

# Inspect last daily run log
python -m breakthrough_engine daily logs --limit 10
```

---

## Constraints Enforced by Code

| Constraint | Mechanism |
|------------|-----------|
| Max 1 run per profile per day | bt_daily_automation_runs DB check |
| Champion-only production | daily_automation.py always reads champion from registry |
| Challenger excluded from production | No daily profile references challenger |
| Review queue insertion | Mandatory in evaluation profile |
| Integrity gate for evaluation | require_integrity_ok=true in profile |
| No automatic promotion | policy_registry.py requires manual promote call |

---

## Phase 9 Actuation Impact on Daily Automation

Phase 9 wired `policy_config` through to the orchestrator. This means:
- When the champion runs in daily automation, it uses `generation_prompt_variant="standard"`
- If/when a challenger is promoted to champion, it will automatically use `generation_prompt_variant="synthesis_focus"` — no code change needed
- Policy snapshots in logs will correctly show which variant was used

The daily automation is policy-actuation-ready.
