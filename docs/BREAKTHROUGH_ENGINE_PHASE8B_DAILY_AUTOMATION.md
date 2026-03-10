# Phase 8B: Bounded Daily Automation Launch

**Phase**: 8B
**Date**: 2026-03-10
**Status**: READY — dry-run validated

---

## Overview

Daily automation is launched with the current `phase5_champion` policy. The `synthesis_focus_v1` challenger is NOT included in daily production runs.

Automatic policy promotion is OFF. The operator retains full control.

---

## Launch Commands

### Dry Run (validate before launch)

```bash
# Evaluation campaign dry run
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy

# Production campaign dry run
python -m breakthrough_engine daily dry-run production_daily_clean_energy
```

### Real Launch (one campaign per profile per day)

```bash
# One evaluation campaign per day
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# One production campaign per day
python -m breakthrough_engine daily run production_daily_clean_energy
```

### Status Check

```bash
# Check today's automation status
python -m breakthrough_engine daily status

# See what's in the review queue
python -m breakthrough_engine review-queue list

# Inspect a specific item
python -m breakthrough_engine review-queue inspect <item_id>
```

---

## Safety Guarantees

1. Max 1 run per profile per calendar day (enforced by `bt_daily_automation_runs`)
2. Dry-run mode never writes to the campaign database
3. Every run produces an operator summary
4. All drafts automatically inserted into review queue
5. No cron scheduler configured by default — operator launches explicitly
6. Champion policy is fixed; challenger cannot enter daily automation automatically

---

## Daily Review Queue Workflow

After each daily run, the operator should:

1. Check the review queue:
   ```bash
   python -m breakthrough_engine review-queue list
   ```

2. Inspect any new items:
   ```bash
   python -m breakthrough_engine review-queue inspect <item_id>
   ```

3. Add review labels for champion (and optionally runner-up):
   ```bash
   python -m breakthrough_engine review-label add \
     --campaign-id <id> \
     --candidate-id <id> \
     --role champion \
     --decision approve \
     --novelty-confidence 0.8 \
     --technical-plausibility 0.8 \
     --commercialization-relevance 0.7
   ```

4. Mark the review queue item as reviewed:
   ```bash
   python -m breakthrough_engine review-queue mark-reviewed <item_id>
   ```

---

## Optional Scheduler Setup

The system does **not** configure a scheduler by default. To optionally set up cron:

```bash
# Example cron (NOT active by default):
# 06:00: evaluation campaign
# 0 6 * * * cd /path/to/breakthrough-engine && .venv/bin/python -m breakthrough_engine daily run evaluation_daily_clean_energy >> runtime/logs/daily_eval.log 2>&1
#
# 07:00: production campaign
# 0 7 * * * cd /path/to/breakthrough-engine && .venv/bin/python -m breakthrough_engine daily run production_daily_clean_energy >> runtime/logs/daily_prod.log 2>&1
```

The operator must explicitly enable this. There is no auto-start.

---

## Profile Details

### evaluation_daily_clean_energy

| Setting | Value |
|---------|-------|
| Campaign profile | `eval_clean_energy_30m` |
| Integrity gate | required |
| Falsification | all finalists |
| Max per day | 1 |
| Review labels | expected |
| Policy | phase5_champion (fixed) |

### production_daily_clean_energy

| Setting | Value |
|---------|-------|
| Campaign profile | `overnight_clean_energy` |
| Integrity gate | best-effort |
| Falsification | top-K |
| Max per day | 1 |
| Review labels | optional |
| Policy | phase5_champion (fixed) |

---

## Promotion Gate (Manual)

Promotion from challenger to probation remains manual:

```bash
# After accumulating evidence, operator decides to promote
python -m breakthrough_engine policy promote <challenger_id> --reason "..."

# To roll back if needed
python -m breakthrough_engine policy rollback --reason "..."
```

**Automatic promotion is OFF in Phase 8B.** The system only produces recommendations.
