# Phase 7C: Telemetry Integrity, Scoring Calibration, 5-Campaign Evaluation Batch

**Branch**: `breakthrough-engine-phase7c-telemetry-calibration`
**Base**: `breakthrough-engine-phase7b-prod-hardening` @ commit `74d86ae`
**Phase start**: 2026-03-09
**Status**: IN PROGRESS

---

## Objective

Phase 7C does not add new research capabilities.
Its sole purpose is to make the engine's telemetry trustworthy enough for long-horizon optimization.

After Phase 7B, the research engine produces credible outputs with real embeddings. But the analysis layer has several data-quality gaps that make multi-campaign comparison unreliable:

1. `elapsed_seconds = 0.0` at campaign level (bug in `_build_pack`)
2. `champion_rationale` always blank (ID mismatch between CampaignManager and DailySearchLadder)
3. `total_candidates_blocked` always 0 (never tracked in `DailyCampaignResult`)
4. `total_finalists` mismatch between DB and campaign summary
5. Incomplete falsification coverage for lower finalists
6. `evidence_strength` near-saturated at 0.98 regardless of evidence count
7. Documentation drift in master plan

---

## Root-Cause Analysis

### Bug 1 & 2: CampaignManager ↔ DailySearchLadder ID mismatch

`CampaignManager.run_campaign()` creates its own `campaign_id`.
`DailySearchLadder.run_campaign()` creates a **different** internal `campaign_id`.
The evaluation pack exporter queries `bt_daily_campaigns WHERE campaign_id = ?` with the **receipt's** campaign_id — which was never written there.

Result: `bt_daily_campaigns` lookup always returns `None` → `elapsed_seconds = 0.0`, `champion_rationale = ""`.

**Fix**: The ladder's internal campaign_id is stored in the `stage_events_json` under the `daily_search_ladder` event details. Extract it from there in `_build_pack`.

Additionally: the campaign receipt's `elapsed_seconds` is correctly populated in the `finally` block (CampaignManager). Read it directly from `bt_campaign_receipts` instead of relying on the bt_daily_campaigns path.

### Bug 3: total_candidates_blocked always 0

`DailyCampaignResult.total_blocked` is declared but never assigned. The novelty blocking happens inside the orchestrator's `_run_novelty_gate`, which marks candidates with `NOVELTY_FAILED`. The count is tracked per-run in `bt_candidates` but not aggregated back to the ladder result or receipt.

**Fix**: In `_build_pack`, count NOVELTY_FAILED candidates directly from `bt_candidates` for the campaign's run_ids.

### Bug 4: total_candidates_generated estimate vs actual

`result.total_candidates_generated = stage1_result.trials_attempted * max(program.candidate_budget, 1)` is an estimate. The actual count may differ.

**Fix**: Count actual rows in `bt_candidates` for the campaign's run_ids.

### Bug 5: Falsification coverage gaps

`_stage3_falsification` only runs on the shortlisted candidates (max `stage3.max_trials` = 3). Many finalists in the broader set came from earlier runs and were never explicitly falsified. Their records show `risk=None, passed=None`.

**Fix**: Mark finalist records with no falsification entry as `risk="MISSING"` rather than leaving them `None`. This makes the gap visible rather than silently missing.

### Bug 6: Evidence strength saturation

Formula: `avg_relevance + diversity_bonus` with no count penalty.
With 2 refs at relevance 0.9 each: score = 0.9 + 0.05 = 0.95.
With 8 refs at relevance 0.9: score = 0.9 + 0.20 = 1.0.
The spread (0.95 vs 1.0) is too small to discriminate evidence quality.

**Fix**: Apply a count-based penalty multiplier. See `scoring.py`.

---

## Deliverables

| # | Deliverable | Status |
|---|-------------|--------|
| A | Telemetry/accounting integrity | DONE |
| B | Elapsed time hardening | DONE |
| C | Evaluation pack v002 | DONE |
| D | Champion/finalist rationale hardening | DONE |
| E | Falsification coverage hardening | DONE |
| F | Evidence-strength calibration | DONE |
| G | Documentation drift cleanup | IN PROGRESS |
| H | Strict telemetry validation run | PENDING |
| I | 5-campaign clean-energy batch | PENDING |
| J | Analysis helpers | PENDING |
| K | Tests | PENDING |
| L | Branch/commit strategy | IN PROGRESS |

---

## Implementation Notes

### evaluation_pack.py changes
- Schema version: `v001` → `v002`
- `_build_pack`: fixed elapsed_seconds, champion_rationale, blocked count, generated count
- Added `accounting_diagnostics` section with `integrity_ok` flag and issue list
- Added `validate_pack_integrity()` function called before writing pack
- MISSING falsification for finalists: explicit `risk="MISSING"` instead of `None`

### scoring.py changes
- Evidence count penalty: `{1: 0.70, 2: 0.82, 3: 0.91, 4: 0.96, 5+: 1.0}`
- Documented in `BREAKTHROUGH_ENGINE_SCORING_CALIBRATION.md`
