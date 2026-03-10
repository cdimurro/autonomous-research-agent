# Breakthrough Engine Review Labels

**Phase**: 7D
**Date**: 2026-03-09
**Branch**: breakthrough-engine-phase7d-eval-profile

---

## Overview

Review labels capture structured human feedback on champion and runner-up finalists
from evaluation-grade campaigns. They are the ground-truth signal for Bayesian policy
optimization.

---

## Label Schema

Each review label record contains:

| Field | Type | Values | Notes |
|-------|------|--------|-------|
| id | TEXT | UUID | Primary key |
| campaign_id | TEXT | Campaign ID | FK to bt_campaign_receipts |
| candidate_id | TEXT | Candidate ID | FK to bt_candidates |
| candidate_title | TEXT | str | Denormalized for export |
| candidate_role | TEXT | champion / runner_up / finalist | Position in this campaign |
| decision | TEXT | approve / reject / defer | Primary review outcome |
| novelty_confidence | REAL | 0.0–1.0 | How confident the reviewer is in the novelty claim |
| technical_plausibility | REAL | 0.0–1.0 | How plausible the mechanism is |
| commercialization_relevance | REAL | 0.0–1.0 | Commercial/deployment potential |
| key_flaw | TEXT | str | Primary weakness identified |
| reviewer_note | TEXT | str | Free-form reviewer notes |
| reviewer | TEXT | str | Reviewer identifier (default: "operator") |
| created_at | TEXT | ISO8601Z | Review timestamp |

---

## Decision Values

| Value | Meaning |
|-------|---------|
| approve | Candidate is high-quality and should advance to publication draft |
| reject | Candidate has a fatal flaw and should be excluded |
| defer | Candidate is interesting but needs more evidence before deciding |

---

## DB Table: bt_review_labels

Added in DB migration 10.

```sql
CREATE TABLE IF NOT EXISTS bt_review_labels (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_title TEXT NOT NULL,
    candidate_role TEXT NOT NULL DEFAULT 'finalist',
    decision TEXT NOT NULL DEFAULT 'defer',
    novelty_confidence REAL DEFAULT 0.5,
    technical_plausibility REAL DEFAULT 0.5,
    commercialization_relevance REAL DEFAULT 0.5,
    key_flaw TEXT DEFAULT '',
    reviewer_note TEXT DEFAULT '',
    reviewer TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
```

---

## CLI Usage

```bash
# Add a review label for a campaign's champion
.venv/bin/python -m breakthrough_engine review-label add \
    --campaign-id <campaign_id> \
    --candidate-id <candidate_id> \
    --role champion \
    --decision approve \
    --novelty-confidence 0.85 \
    --technical-plausibility 0.80 \
    --commercialization-relevance 0.70 \
    --key-flaw "Requires rare catalyst" \
    --note "Strong hypothesis but catalyst sourcing is a concern"

# List review labels for a campaign
.venv/bin/python -m breakthrough_engine review-label list --campaign-id <campaign_id>

# Export all review labels as CSV
.venv/bin/python -m breakthrough_engine review-label export --output review_labels.csv
```

---

## Use in Policy Optimization

Review labels provide the ground-truth signal `P(human_approves | score, domain, model)`:

- `approve` → positive reward signal
- `reject` → negative reward signal
- `defer` → neutral / uncertainty signal

The Bayesian evaluator can use these labels to update posteriors for:
- `novelty_score` calibration
- `evidence_strength` calibration
- Domain-specific approval rates

---

## Export Format

Labels are included in the batch summary as `review_labels.csv`:

```
campaign_id,candidate_id,candidate_title,candidate_role,decision,
novelty_confidence,technical_plausibility,commercialization_relevance,
key_flaw,reviewer_note,reviewer,created_at
```

---

## Labels Required for Evaluation-Grade Batches

For each campaign in an evaluation-grade batch:
- Champion: **required** review label
- Runner-up (rank 2): **expected** review label
- Other finalists: optional

A batch with zero review labels cannot be used for policy optimization.
