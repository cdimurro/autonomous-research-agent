# Phase 8 Baselines Reference

**Branch**: `breakthrough-engine-phase8-reviewed-learning`
**Date**: 2026-03-09

---

## Overview

The Breakthrough Engine maintains two trusted baselines:

| Baseline | File | Purpose | When to Use |
|----------|------|---------|-------------|
| Phase 5 validated | `runtime/baselines/phase5_validated_benchmark.json` | Long-term regression on core quality (deterministic) | Champion promotion, regression gate |
| Phase 7D reviewed | `runtime/baselines/phase7d_reviewed_baseline.json` | Reviewed-signal policy-learning comparison | Policy posterior anchoring, batch comparison |

**Do not use Phase 5 for reviewed policy comparison.** Phase 5 was generated with FakeCandidateGenerator and MockEmbeddingProvider (deterministic test mode). It measures algorithmic regression, not real-world quality.

**Do not use Phase 7D for algorithmic regression.** Phase 7D uses real embeddings and real candidates. It is not reproducible in the same deterministic sense as Phase 5.

---

## Phase 5 Frozen Baseline

| Field | Value |
|-------|-------|
| File | `runtime/baselines/phase5_validated_benchmark.json` |
| Tag | `breakthrough-engine-phase5-validated` |
| Commit | `29d68a39` |
| Created | 2026-03-08 |
| Mode | deterministic_test (FakeCandidateGenerator + MockEmbeddingProvider) |
| Schema | Phase 6 benchmark schema |

### Metrics

| Metric | Value |
|--------|-------|
| Draft creation rate | 1.000 (3/3 runs) |
| Novelty block rate | 0.000 (0/12 blocked) |
| Synthesis fit pass rate | 1.000 (12/12) |
| Review-worthy rate | 1.000 (6/6 ≥ 0.60) |
| Top candidate score | 0.912 |
| Mean evidence balance | 0.918 |

### Usage

```bash
# Run deterministic benchmark and compare to Phase 5 baseline
python -m breakthrough_engine baseline compare
```

Regression threshold: no metric may regress > 0.05 from Phase 5 baseline.

---

## Phase 7D Reviewed Baseline

| Field | Value |
|-------|-------|
| File | `runtime/baselines/phase7d_reviewed_baseline.json` |
| Branch | `breakthrough-engine-phase7d-eval-profile` |
| Commit | `3381cca` |
| Created | 2026-03-09 |
| Mode | evaluation-grade (real OllamaEmbeddingProvider + real OllamaCandidateGenerator) |
| Profile | `eval_clean_energy_30m` |
| Schema version | v003 |
| Campaigns | 5 (all integrity_ok=True, all falsification_complete=True) |

### Batch Metrics

| Metric | Value |
|--------|-------|
| Total candidates generated | 74 |
| Total candidates blocked | 23 (31.1%) |
| Total finalists | 27 |
| Champion score min | 0.883 |
| Champion score max | 0.931 |
| Champion score mean | 0.905 |
| Review labels collected | 0 (pending — Phase 8 adds labeling tooling) |

### Usage

```bash
# Check Phase 7D reviewed baseline
python -m breakthrough_engine baseline show phase7d_reviewed

# Compare current batch against Phase 7D reviewed baseline
python -m breakthrough_engine baseline compare-reviewed --baseline phase7d_reviewed --batch <batch_id>
```

Regression thresholds vs Phase 7D reviewed baseline:
- `champion_score_mean`: no regression > 0.05
- `block_rate`: no regression > 0.10 (higher block rate is OK up to a point)
- `falsification_complete_rate`: must remain 1.00
- `integrity_ok_rate`: must remain 1.00

---

## Baseline CLI Commands

```bash
# List all frozen baselines
python -m breakthrough_engine baseline list

# Show a specific baseline
python -m breakthrough_engine baseline show phase5_validated
python -m breakthrough_engine baseline show phase7d_reviewed

# Freeze a new batch as a named baseline (use carefully)
python -m breakthrough_engine baseline freeze --name <name> --batch-id <batch_id>

# Compare deterministic benchmark to Phase 5 baseline (existing)
python -m breakthrough_engine baseline compare

# Compare a reviewed batch to Phase 7D baseline
python -m breakthrough_engine baseline compare-reviewed --baseline phase7d_reviewed --batch <batch_id>
```

---

## Baseline Selection Logic

| Use Case | Correct Baseline |
|----------|-----------------|
| Check for algorithmic regression before any champion promotion | Phase 5 validated |
| Anchor Bayesian posteriors for a new policy's first campaign | Phase 7D reviewed |
| Detect score drift across real campaigns over time | Phase 7D reviewed |
| Validate that a new schema doesn't break deterministic behavior | Phase 5 validated |
| Check whether reviewed batch quality has improved | Phase 7D reviewed |
