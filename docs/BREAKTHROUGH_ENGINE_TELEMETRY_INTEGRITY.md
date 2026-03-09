# Breakthrough Engine Telemetry Integrity

**Phase**: 7C
**Date**: 2026-03-09
**Branch**: breakthrough-engine-phase7c-telemetry-calibration

---

## Overview

This document records the telemetry inconsistencies observed in Phase 7B overnight campaigns, their root causes, and the fixes applied in Phase 7C.

---

## Observed Inconsistencies (Phase 7B)

### Campaign f01a0a7c72304481 — Second Overnight Run

| Field | Reported (campaign summary) | Evaluation Pack | Source of Truth |
|-------|----------------------------|-----------------|-----------------|
| elapsed_seconds | 0.0 | 0.0 | BROKEN (should be ~2487s) |
| champion_rationale | (blank) | (blank) | BROKEN |
| total_candidates_blocked | 0 | 0 | BROKEN (real count unknown) |
| total_finalists | 30 (pre-export claim) | 27 (pack) | 27 (DB count) |
| stage timing | 2487.25s (stage detail) | 0.0 (top-level) | BROKEN |

---

## Root Causes

### 1. CampaignManager ↔ DailySearchLadder ID mismatch

**File**: `breakthrough_engine/evaluation_pack.py`, `_build_pack()`

**Problem**:
- `CampaignManager.run_campaign()` creates `campaign_id = new_id()` → stored in `bt_campaign_receipts.campaign_id`
- `DailySearchLadder.run_campaign()` creates a DIFFERENT `campaign_id = new_id()` → stored in `bt_daily_campaigns.campaign_id`
- `_build_pack()` queries `bt_daily_campaigns WHERE campaign_id = ?` using the **receipt's** campaign_id
- Query returns `None` every time → `elapsed_seconds = 0.0`, `champion_rationale = ""`

**Why not caught earlier**: The pack still exports (gracefully handles None) but silently produces wrong values.

**Fix**:
1. Extract ladder's campaign_id from `stage_events_json` (the `daily_search_ladder` event stores it in `details.campaign_id`)
2. Use extracted ID for `bt_daily_campaigns` lookup
3. Also read `elapsed_seconds` directly from `bt_campaign_receipts.elapsed_seconds` (which IS populated correctly in the `finally` block)

### 2. total_candidates_blocked always 0

**File**: `breakthrough_engine/daily_search.py`, `DailyCampaignResult`

**Problem**:
- `total_blocked: int = 0` is declared but never set
- Blocking happens in `orchestrator.py` `_run_novelty_gate()` → marks candidates `NOVELTY_FAILED` in DB
- These counts are never aggregated back to the ladder result or campaign receipt

**Fix**:
- In `_build_pack()`, count `bt_candidates` rows with `status='novelty_failed'` for the campaign's run_ids

### 3. total_candidates_generated estimate vs actual

**File**: `breakthrough_engine/daily_search.py`, `run_campaign()`

**Problem**:
```python
result.total_candidates_generated = stage1_result.trials_attempted * max(program.candidate_budget, 1)
```
This is an arithmetic estimate that may not match actual DB rows.

**Fix**: Count actual `bt_candidates` rows for the campaign's run_ids in `_build_pack()`.

### 4. Incomplete falsification for non-shortlisted finalists

**File**: `breakthrough_engine/daily_search.py`, `_stage3_falsification()`

**Problem**:
- Stage 3 only falsifies up to `stage3.max_trials` (= 3) candidates
- Candidates that are finalists but not in top-3 shortlist were never falsified
- Their records show `risk=None, passed=None` — silently missing

**Fix**:
- In `_build_pack()`, candidates with `status='finalist'` and no falsification summary get `risk="MISSING"` (explicit, not None)
- Added to `validate_pack_integrity()` check

---

## Fixes Applied (Phase 7C)

### evaluation_pack.py

1. **elapsed_seconds**: Read from `bt_campaign_receipts.elapsed_seconds` (Line: `pack.elapsed_seconds = receipt["elapsed_seconds"] or 0.0`)

2. **champion_rationale**: Extract ladder campaign_id from stage_events before querying bt_daily_campaigns:
   ```python
   for ev in stage_events:
       if ev.get("stage_name") == "daily_search_ladder":
           ladder_campaign_id = ev.get("details", {}).get("campaign_id", "")
   ```

3. **total_candidates_blocked**: Direct DB count:
   ```python
   SELECT COUNT(*) FROM bt_candidates WHERE run_id IN (...) AND status = 'novelty_failed'
   ```

4. **total_candidates_generated**: Direct DB count:
   ```python
   len(rows)  # all bt_candidates for campaign's run_ids
   ```

5. **accounting_diagnostics section**: New v002 field with `integrity_ok` flag and `issues` list

6. **validate_pack_integrity()**: Checks elapsed, rationale, and falsification before export

7. **Falsification MISSING sentinel**: Finalists without falsification get `risk="MISSING"` instead of `None`

8. **Schema version**: v001 → v002

---

## How to Verify Telemetry Health

```bash
cd /Users/openclaw/breakthrough-engine

# Re-export an existing campaign to see v002 diagnostics
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine evaluation-pack export <campaign_id> --overwrite

# Check the diagnostics section
python3 -c "
import json
with open('runtime/evaluation_packs/<campaign_id>/evaluation_pack.json') as f:
    p = json.load(f)
diag = p.get('accounting_diagnostics', {})
print('Integrity OK:', diag.get('integrity_ok'))
print('Issues:', diag.get('issues'))
print('Elapsed:', p['campaign']['elapsed_seconds'])
print('Rationale:', repr(p.get('champion_rationale', '')[:80]))
print('DB blocked:', diag.get('db_blocked'))
print('DB generated:', diag.get('db_generated'))
"
```

---

## Source-of-Truth Rules (Post-7C)

| Field | Source of Truth |
|-------|----------------|
| elapsed_seconds | `bt_campaign_receipts.elapsed_seconds` |
| champion_rationale | `bt_daily_campaigns.result_json["champion_selection_rationale"]` via ladder_campaign_id |
| total_candidates_generated | Count of `bt_candidates` rows for campaign run_ids |
| total_candidates_blocked | Count of `bt_candidates` with status='novelty_failed' for run_ids |
| total_finalists | Count of `bt_candidates` with status='finalist' for run_ids |
| total_shortlisted | `bt_campaign_receipts.total_shortlisted` (from ladder result) |
| embedding_provider | `bt_campaign_receipts.embedding_provider` (via config_json) |
