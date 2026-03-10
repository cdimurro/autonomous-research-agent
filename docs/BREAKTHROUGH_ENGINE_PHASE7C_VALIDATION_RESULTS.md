# Phase 7C Validation Results

**Branch**: `breakthrough-engine-phase7c-telemetry-calibration`
**Date**: 2026-03-09
**Executed by**: Claude Sonnet 4.6 (Phase 7C-B session)

---

## Phase A: Eval Pack v002 Re-export Verification

**Campaign**: `f01a0a7c72304481` (overnight_clean_energy, completed_with_draft)

### Command run

```bash
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine evaluation-pack export f01a0a7c72304481 --overwrite
```

### v002 Field Verification

| Field | Expected | Actual | Status |
|-------|----------|--------|--------|
| schema_version | v002 | v002 | PASS |
| elapsed_seconds | Non-zero (was 0.0 in v001) | 2488.0s | PASS |
| champion_rationale | Non-empty (was blank in v001) | "Score 0.957, APPROVE, beat 4..." | PASS |
| ladder_campaign_id | Recovered from stage_events | 389d956e3779475b | PASS |
| elapsed_seconds_source | bt_campaign_receipts | bt_campaign_receipts | PASS |
| accounting_diagnostics | Present | Present | PASS |
| db_generated | Actual DB count | 69 | PASS |
| db_blocked | NOVELTY_FAILED count | 9 | PASS |
| db_finalists | Finalist DB count | 27 | PASS |
| MISSING falsification sentinel | 24 finalists marked MISSING | 24/27 MISSING, 3/27 real | PASS |
| models.embedding_provider | OllamaEmbeddingProvider | OllamaEmbeddingProvider(nomic-embed-text) | PASS |

### Integrity Status

`integrity_ok = False` — expected, documented issues:

| Issue | Root Cause | Disposition |
|-------|-----------|-------------|
| generated_count_mismatch: receipt=80, db=69 | Receipt uses arithmetic estimate (trials×budget=80); actual DB has 69 rows | KNOWN/EXPECTED — documented in telemetry integrity doc |
| falsification_missing: 24 finalist(s) | Stage 3 only falsifies top-3 shortlist; 24 of 27 finalists not falsified | KNOWN/EXPECTED — documented in Phase 7C status |

**Assessment**: `integrity_ok = False` is correct behavior. The two issues are documented known limitations, not regressions. All critical v002 telemetry fixes are verified working.

### Champion

- **Title**: Thermal Conductivity Enhancement via Graphene-Interdigitated PCM Capsules
- **Final score**: 0.957
- **Falsification risk**: medium (passed=True) — shortlisted candidate with real falsification
- **Evidence strength**: 0.98 (pre-calibration score, not recalculated retroactively per scoring calibration policy)

### Top 5 Finalists

| Rank | Score | Title |
|------|-------|-------|
| 1 | 0.957 | Thermal Conductivity Enhancement via Graphene-Interdigitated PCM Capsules |
| 2 | 0.947 | Sub-Ambient Thermal Storage via Radiative Sky-Cooling PCM En... |
| 3 | 0.944 | Latent Heat Recovery via High-Efficiency TPV Radiative Coupling |
| 4 | 0.937 | Low-Temp MOF Radiative Insulation for Passive Cooling |
| 5 | 0.929 | Thermal Gradient Harvesting via Perovskite-TPV Hybrid Insula... |

### Phase A Verdict: PASS

All core telemetry fixes are confirmed working on a real campaign artifact. Pack v002 is ready for use.

---

## Phase B: Strict Validation Campaign

**Campaign**: `2bfaec77b7314b6a` (smoke_10m, completed_with_draft)

### Command run

```bash
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine campaign run --profile smoke_10m
```

### Results

| Field | Value |
|-------|-------|
| campaign_id | 2bfaec77b7314b6a |
| profile | smoke_10m |
| status | completed_with_draft |
| elapsed_seconds | 513.0 (from bt_campaign_receipts, not 0.0) |
| generated | 7 |
| blocked | 3 |
| finalists | 3 |
| shortlisted | 2 |
| champion | Quantum Dot Spectral Tuning for Low-Light Aqueous Systems |
| champion_score | 0.92054 |
| champion_evidence_strength | 0.8036 (calibrated: 0.98 × 0.82 = 0.804) |
| champion_falsification | risk=medium, passed=True |
| champion_rationale | "Score 0.921, APPROVE, beat 1 runner-up(s)..." |
| embedding_provider | OllamaEmbeddingProvider(nomic-embed-text) |
| integrity_ok | False (expected known issues only) |

### Telemetry integrity check

- elapsed_seconds = 513.0 ✓ (from bt_campaign_receipts)
- champion_rationale populated ✓
- real embeddings confirmed ✓
- evidence_strength calibration active ✓ (0.804, not ~0.98)
- MISSING falsification sentinel: 1 of 3 finalists (expected: only 2 shortlisted)

### Phase B Verdict: PASS

The corrected telemetry path is trustworthy. 5-campaign batch authorized.

---

## Phase C: 5-Campaign Batch

**Status**: COMPLETE — all 5 campaigns completed_with_draft

### Blocker Found and Fixed

**Campaign 4** (eaecd0ac79724763): champion was missing from the v002 pack due to a timestamp format mismatch. A run starting at `2026-03-09T23:57:47.318316` was excluded by the window query because SQLite string comparison treats `.` < `Z`.

**Fix applied**: timestamp normalization via `substr(started_at, 1, 19)` comparison (2 new tests, both passing).

### Batch Results

| # | Campaign ID | Status | Elapsed | Champion Score | Champion Title |
|---|-------------|--------|---------|----------------|----------------|
| 1 | 338e0f4f25104af9 | completed_with_draft | 507s | 0.8740 | Hybrid Electrolyte-Photocatalytic Interface for Tandem Water Splitting |
| 2 | 715d90d816c74256 | completed_with_draft | 540s | 0.9155 | Anion Exchange Membrane Cross-Linking for Seawater Resistance |
| 3 | e415af49809b492b | completed_with_draft | 481s | 0.9205 | High-Energy Solid-State Battery Integration for Offshore Wake Stabilization |
| 4 | eaecd0ac79724763 | completed_with_draft | 540s | 0.8830 | Piezo-Electric Wake Shielding Using Sulfide-Based Nanocomposites |
| 5 | 7ba8ad82393a4376 | completed_with_draft | 542s | 0.9075 | CO2-Derived Carbonate Precursors for Solid-State Battery Interfaces |

All 5 evaluation packs exported with schema v002.
All champions: falsification_passed=True, risk=medium.
All evidence_strength: 0.8036 (calibrated v002 count penalty confirmed active).

### Phase C Verdict: PASS
