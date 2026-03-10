# Phase 7D Implementation Status

**Branch**: `breakthrough-engine-phase7d-eval-profile`
**Date**: 2026-03-09 → 2026-03-10
**Status**: COMPLETE

---

## Starting State

| Field | Value |
|-------|-------|
| Branch | breakthrough-engine-phase7c-telemetry-calibration |
| Commit | 8ec8c36 |
| Tests | 581 passing, 0 failures |
| Schema version | v002 |
| Generation model | qwen3.5:9b-q4_K_M |
| Embedding model | nomic-embed-text (OllamaEmbeddingProvider) |
| Integrity failures | 2 (generated_count_mismatch, falsification_missing) |
| Profiles | smoke_10m, pilot_30m, overnight_clean_energy |
| Falsification coverage | Top-2 shortlisted only (smoke_10m) |

---

## Final State

| Field | Value |
|-------|-------|
| Tests | 614+ passing, 0 failures |
| Schema version | v003 (evaluation-grade), v002 (smoke/pilot) |
| Integrity failures | 0 |
| Profiles | + eval_clean_energy_30m (evaluation-grade, 30m) |
| Falsification coverage | ALL finalists (falsify_all_finalists=True in eval profile) |
| Batch campaigns | 5 × eval_clean_energy_30m, all integrity_ok=True |

---

## Deliverable Status

| Deliverable | Status | Notes |
|-------------|--------|-------|
| A. Generated count fix | DONE | `_run_single_trial` returns actual DB row count; no arithmetic estimate |
| B. Full finalist falsification | DONE | `falsify_all_finalists=True` in eval profile; all finalists falsified |
| C. Evaluation profile | DONE | `config/campaign_profiles/eval_clean_energy_30m.yaml` |
| D. Eval pack v003 / integrity green | DONE | Schema v003, hard ValueError on eval-grade integrity failure |
| E. Structured review labels | DONE | `bt_review_labels` table (migration 10), CLI subcommands |
| F. Strict validation run | DONE | 1 campaign, integrity_ok=True, falsification_complete=True |
| G. 5-campaign reviewed batch | DONE | 5 campaigns, all integrity_ok=True, all falsification_complete=True |
| H. Testing | DONE | 33 tests in test_phase7d.py |
| I. Docs | DONE | Plan, Status, Evaluation Profile, Review Labels, Batch Report |

---

## Root Causes Fixed

### `generated_count_mismatch`

**Root cause**: `DailyCampaignResult.total_candidates_generated` used arithmetic estimate
(`trials_attempted * candidate_budget`) which differed from actual DB row count because the
orchestrator may generate more or fewer candidates than the configured budget.

**Fix**: `_run_single_trial()` now counts actual DB rows (`list_candidates_for_run(run_id)`)
and returns the count as the third element of a 3-tuple. `_stage1_exploration()` accumulates
this across all trials and stores it in `details["actual_candidates_generated"]`.
`run_campaign()` reads this instead of computing arithmetic estimate.

### `falsification_missing`

**Root cause**: Stage 3 passed only `shortlisted[:stage.max_trials]` to falsification.
For smoke_10m with `stage2_shortlist_size=2`, only 2 of 6+ finalists were falsified, leaving
the rest with `falsification_risk="MISSING"`.

**Fix**: New `falsify_all_finalists: bool = False` flag on `LadderConfig` and `CampaignProfile`.
When `True`, all finalists (not just the shortlisted top-K) are passed to `_stage3_falsification`.
Set to `True` in `eval_clean_energy_30m.yaml`.

### Time-window boundary contamination

**Root cause**: `_build_pack()` used `<= completed_at` for the run time-window query. When
two campaigns ran back-to-back and the second campaign's first run started at the same second
as the first campaign's `completed_at`, it was counted in the first campaign's `db_generated`.

**Fix**: Changed to strict `< completed_at` boundary in `evaluation_pack.py`.

---

## Key Files Modified

| File | Change |
|------|--------|
| `breakthrough_engine/daily_search.py` | 3-tuple return from `_run_single_trial`, actual candidate count accumulation, `falsify_all_finalists` support |
| `breakthrough_engine/campaign_manager.py` | `falsify_all_finalists` in `CampaignProfile` and `LadderConfig` construction |
| `breakthrough_engine/db.py` | Migration 10: `bt_review_labels` table; `save_review_label`, `get_review_labels_for_campaign`, `list_all_review_labels` |
| `breakthrough_engine/evaluation_pack.py` | Schema v003, hard integrity gate, time-window `< completed_at` fix, `_load_review_labels`, `_write_review_labels_csv`, `falsification_complete` flag |
| `breakthrough_engine/cli.py` | `review-label` subcommands (add, list, export) |
| `config/campaign_profiles/eval_clean_energy_30m.yaml` | New evaluation-grade profile |
| `tests/test_breakthrough/test_phase7d.py` | 33 new tests |
| `tests/test_breakthrough/test_phase7b.py` | Updated migration assertion (>= 9, now at 10) |

---

## Batch Results

### Strict Validation Campaign

Ran `eval_clean_energy_30m` once before the batch to confirm the new profile works end-to-end:
- integrity_ok: True
- falsification_complete: True
- schema_version: v003
- issues: []

### 5-Campaign Reviewed Batch

| Campaign | Candidates | Blocked | Finalists | Champion Score | Integrity | Falsif. |
|----------|-----------|---------|-----------|----------------|-----------|---------|
| a5ee0f0da9d64406 | 14 | 4 (28.6%) | 6 | 0.89554 | ✓ | ✓ |
| 1e9946098daa4a24 | 15 | 8 (53.3%) | 5 | 0.89754 | ✓ | ✓ |
| 0585efe9c6d34425 | 14 | 8 (57.1%) | 4 | 0.88304 | ✓ | ✓ |
| 37bc8e152f794f17 | 15 | 2 (13.3%) | 6 | 0.93054 | ✓ | ✓ |
| ba50214d47654da3 | 16 | 1 (6.2%) | 6 | 0.91854 | ✓ | ✓ |
| **Total** | **74** | **23 (31.1%)** | **27** | 0.883–0.931 | **5/5** | **5/5** |

**Best champion**: Carrier Extraction Optimization in Perovskite/Quantum Dot Hybrid Tandems (0.93054)
**Weakest champion**: Lignin-Derived Sulfide Electrolytes for High-Energy Density Bio-Battery Storage (0.88304)

Full batch artifacts: `runtime/evaluation_batches/phase7d_batch_20260310/`

---

## Test Coverage

```
tests/test_breakthrough/test_phase7d.py  — 33 tests
  TestActualCandidateCount              — generated count fix
  TestFalsifyAllFinalists               — falsify_all_finalists flag
  TestEvalProfileConfig                 — eval_clean_energy_30m YAML
  TestEvalGradeIntegrityGate            — hard fail on integrity failure
  TestReviewLabelSchema                 — bt_review_labels table
  TestReviewLabelCRUD                   — insert / retrieve / list
  TestReviewLabelCLI                    — CLI subcommands
  TestSchemaV003                        — v003 for evaluation-grade
  TestTimeBoundaryFix                   — < completed_at strict boundary
  TestFalsificationCompleteFlag         — falsification_complete in diagnostics
```
