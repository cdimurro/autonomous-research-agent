# Bounded Daily Automation

**Phase**: 8
**Branch**: `breakthrough-engine-phase8-reviewed-learning`
**Date**: 2026-03-09

---

## Overview

Bounded daily automation runs one evaluation campaign and one production campaign per day. It is designed to be:

- **Safe**: Never runs unattended indefinitely
- **Inspectable**: Every run produces a clear operator summary
- **Reviewable**: Every draft goes into the review queue
- **Reversible**: Dry-run mode always available

---

## Daily Profiles

### evaluation_daily_clean_energy

Used for policy evaluation and Bayesian posterior updates.

| Field | Value |
|-------|-------|
| Profile | `eval_clean_energy_30m` |
| Mode | evaluation-grade |
| Schema | v003 |
| Integrity gate | required |
| Falsification | all finalists |
| Review labels | expected (champion + runner-up) |
| Output | Evaluation pack + review queue entry |
| Max per day | 1 |

```bash
# Run evaluation daily campaign
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Dry run (no actual campaign, just shows what would happen)
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
```

### production_daily_clean_energy

Used for production-quality search campaigns with publication drafts.

| Field | Value |
|-------|-------|
| Profile | `overnight_clean_energy` |
| Mode | production (real embeddings, real generator) |
| Schema | v002 |
| Integrity gate | best-effort (not hard fail) |
| Falsification | top-K shortlisted |
| Review labels | optional |
| Output | Campaign receipt + production packet + review queue entry if draft |
| Max per day | 1 |

```bash
# Run production daily campaign
python -m breakthrough_engine daily run production_daily_clean_energy

# Dry run
python -m breakthrough_engine daily dry-run production_daily_clean_energy
```

---

## Daily Run Outcomes

Every daily run produces one of these outcomes:

| Outcome | Meaning |
|---------|---------|
| `completed_with_draft` | Campaign completed, draft produced, inserted into review queue |
| `completed_no_draft` | Campaign completed, no draft produced (all candidates below threshold) |
| `aborted_preflight` | Campaign aborted during preflight check |
| `aborted_runtime` | Campaign aborted due to runtime error |

---

## Review Queue Integration

When a draft exists (`completed_with_draft`), the system automatically inserts a review queue entry containing:

- Campaign ID and timestamp
- Champion packet (title, score, domain)
- Falsification summary
- Policy used
- Reviewer label placeholder
- Operator action required

---

## Operator Workflow

### Morning After Inspection

```bash
# Check what happened in yesterday's daily runs
python -m breakthrough_engine daily status --date yesterday

# See what's in the review queue
python -m breakthrough_engine review-queue list

# Inspect a specific review queue item
python -m breakthrough_engine review-queue inspect <item_id>

# Add a review label to yesterday's champion
python -m breakthrough_engine review-label add \
    --campaign-id <id> \
    --candidate-id <id> \
    --role champion \
    --decision approve \
    --novelty-confidence 0.85 \
    --technical-plausibility 0.80 \
    --commercialization-relevance 0.70
```

### Launch Commands

```bash
# Single evaluation campaign (bounded, safe)
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Single production campaign (bounded, safe)
python -m breakthrough_engine daily run production_daily_clean_energy

# Dry run any profile
python -m breakthrough_engine daily dry-run <profile_name>

# Check daily automation status
python -m breakthrough_engine daily status
```

---

## Safety Constraints

1. Each profile may run at most once per calendar day (enforced by `bt_daily_automation_runs`)
2. If a profile already ran today, `daily run` exits with a warning (not an error)
3. Dry-run mode never writes to the campaign database
4. All daily runs log their outcome and policy used to `bt_daily_automation_runs`
5. No cron job or scheduler is enabled by default — operator must launch explicitly

---

## Scheduling (Optional)

The daily automation is designed to be triggered by cron or any scheduler, but does **not** configure this by default:

```bash
# Example cron entry (NOT configured by default):
# 06:00 daily: evaluation campaign
# 0 6 * * * cd /path/to/breakthrough-engine && .venv/bin/python -m breakthrough_engine daily run evaluation_daily_clean_energy >> runtime/logs/daily_eval.log 2>&1

# 07:00 daily: production campaign
# 0 7 * * * cd /path/to/breakthrough-engine && .venv/bin/python -m breakthrough_engine daily run production_daily_clean_energy >> runtime/logs/daily_prod.log 2>&1
```

The operator must explicitly configure scheduling. The system will not auto-schedule.

---

## Artifacts per Daily Run

| Artifact | Location |
|----------|----------|
| Campaign receipt | `runtime/campaign_receipts/<campaign_id>/` |
| Evaluation pack (eval profile) | `runtime/evaluation_packs/<campaign_id>/` |
| Daily run record | `bt_daily_automation_runs` table |
| Review queue entry | `bt_review_queue` table |
| Operator log | `runtime/logs/daily_<date>.log` |
