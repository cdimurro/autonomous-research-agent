# Phase 7C Execution Status

**Branch**: `breakthrough-engine-phase7c-telemetry-calibration`
**Session start**: 2026-03-09
**Last updated**: 2026-03-09 (session start)

---

## Current State Snapshot

| Item | Value |
|------|-------|
| Branch | breakthrough-engine-phase7c-telemetry-calibration |
| Commit | 8f7cd02 |
| Schema version | v002 |
| Test status | 579 passing, 0 failures |
| Generation model | qwen3.5:9b-q4_K_M |
| Embedding model | nomic-embed-text (via Ollama) |
| BT_EMBEDDING_MODEL | Must be set: nomic-embed-text |
| Ollama status | RUNNING (confirmed at session start) |
| Available models | nomic-embed-text:latest, qwen3.5:9b-q4_K_M |

---

## Profile Names

| Profile | Type | Description |
|---------|------|-------------|
| overnight_clean_energy | overnight | Full overnight clean-energy run |
| smoke_10m | smoke | 10-minute bounded validation |

---

## Known Issues from Phase 7C Final Report

1. `total_candidates_blocked` in v001 packs is always 0 — re-export with v002 to fix
2. `champion_rationale` was blank in v001 packs — fixed in v002 via ladder_campaign_id recovery
3. `elapsed_seconds` was 0.0 in v001 packs — fixed in v002 via bt_campaign_receipts lookup
4. Falsification only covers top-3 (shortlist) — other finalists show MISSING in v002
5. Evidence-strength scoring was near-saturated for 2 refs — count penalty added in v002

---

## Existing Campaigns

| campaign_id | profile | status |
|-------------|---------|--------|
| f01a0a7c72304481 | overnight_clean_energy | completed_with_draft |
| b80c979d75144fb8 | smoke_10m | completed_with_draft |
| b87513b86b6f4b1f | overnight_clean_energy | completed_with_draft |

---

## Phase Execution Tracking

| Phase | Description | Status | Result |
|-------|-------------|--------|--------|
| A | Re-export campaign f01a0a7c72304481 with v002 | COMPLETE | PASS — all telemetry fixes confirmed |
| B | Strict validation campaign (smoke_10m) | COMPLETE | PASS — campaign 2bfaec77b7314b6a |
| C | 5-campaign clean-energy batch | COMPLETE | PASS — all 5 completed_with_draft |
| D | Batch summary + analysis pack | COMPLETE | runtime/evaluation_batches/phase7c_batch_20260309/ |
| E | Morning-after inspection commands | COMPLETE | docs/BREAKTHROUGH_ENGINE_PHASE7C_BATCH_RESULTS.md |

---

## Blocker Found and Fixed

**Run timestamp normalization (7C-B)**:
- Campaign 4 (eaecd0ac79724763) champion was missing from pack
- Root cause: `substr(started_at,1,19)` comparison needed instead of raw string `>=`
- Fix: evaluation_pack.py run-matching query (minimal, 1 SQL change)
- Tests: 2 new tests added, all 581 passing

---

## Final Test Count

- 579 tests at Phase 7C start
- +2 new tests (TestRunTimestampNormalization)
- **581 total, 0 failures**
