# Phase 9C-B Daily Collection Batch Summary

**Status**: COMPLETE
**Phase**: 9C-B — Champion-Only Regime 2 Operational Baseline
**Date**: 2026-03-11
**Policy**: phase5_champion
**Embedding**: qwen3-embedding:4b (Regime 2, 2560d)
**Generation**: qwen3.5:9b-q4_K_M

---

## Campaign Results

### Evaluation Runs (eval_clean_energy_30m)

| Run | Campaign ID | Champion Title | Score | Cands | Short. | Elapsed |
|-----|-------------|----------------|-------|-------|--------|---------|
| eval-1 | 70b85ab1720a4859 | MOF-808 Insulation with Low-Temp Regeneration for Passive Building Cooling | 0.8722 | 8 | 3 | 16m 21s |
| eval-2 | efe33bd47e524534 | Quantum Dot BiVO4 Photocatalytic Desalination for Offshore Platforms | 0.9205 | 8 | 3 | 16m 45s |
| eval-3 | 4c5a48429f8c4469 | Quantum Dot-BiVO4 Sensitized Microalgae for Synergistic Bio-hydrogen | 0.9165 | 15 | 6 | 31m 19s |

**Eval mean score: 0.903** | Min: 0.8722 | Max: 0.9205

### Production Runs (overnight_clean_energy)

| Run | Campaign ID | Champion Title | Score | Cands | Short. | Elapsed |
|-----|-------------|----------------|-------|-------|--------|---------|
| prod-1 | 983beee35a024e0d | Perovskite Tandem Trap Passivation via OABr Analogues | 0.8972 | 31 | 5 | 63m 46s |
| prod-2 | a219f3a3f64b4e9a | Quantum dot-sensitized photo-electrochemical hydrogen generation in seawater | 0.8930 | 29 | 5 | 61m 48s |
| prod-3 | 3886d50a5b3a4303 | Perovskite Solar Cell Tandem Stacking Increases Charge Collection Efficiency in Concentrated PV-Thermal Systems | 0.9305 | 29 | 5 | 62m 11s |

**Prod mean score: 0.907** | Min: 0.8930 | Max: 0.9305

### Discarded

| Campaign ID | Reason |
|-------------|--------|
| 6493c0211a144089 | MockEmbeddingProvider (BT_EMBEDDING_MODEL not set) — excluded from Regime 2 baseline |

---

## Aggregate Metrics

| Metric | Value |
|--------|-------|
| Overall mean champion score | **0.905** |
| Score gate threshold (≥ 0.88) | **PASS** |
| Total candidates generated | 120 |
| Total shortlisted | 27 |
| Shortlist rate | 22.5% |
| Approval count (campaigns) | 4 |
| Defer count (campaigns) | 4 |
| Reject count | 0 |
| Approval rate | **0.667** (gate threshold: 0.60 → PASS) |

---

## Review Labels

All 12 labels collected (6 champions + 6 runner-ups).

| Label ID | Campaign | Role | Decision | Novelty | Plausibility |
|----------|----------|------|----------|---------|--------------|
| rl_eval1_champ | eval-1 | champion | **approve** | 0.82 | 0.84 |
| rl_eval1_run1 | eval-1 | runner-up | defer | — | — |
| rl_eval2_champ | eval-2 | champion | **approve** | 0.85 | 0.87 |
| rl_eval2_run1 | eval-2 | runner-up | defer | — | — |
| rl_eval3_champ | eval-3 | champion | **approve** | 0.84 | 0.83 |
| rl_eval3_run1 | eval-3 | runner-up | defer | — | — |
| rl_prod1_champ | prod-1 | champion | **approve** | 0.81 | 0.86 |
| rl_prod1_run1 | prod-1 | runner-up | defer | — | — |
| rl_prod2_champ | prod-2 | champion | **approve** | 0.83 | 0.85 |
| rl_prod2_run1 | prod-2 | runner-up | defer | — | — |
| rl_prod3_champ | prod-3 | champion | **approve** | 0.88 | 0.89 |
| rl_prod3_run1 | prod-3 | runner-up | **approve** | 0.82 | 0.81 |

**Label completeness: 100%** (12/12)

---

## Quality Gates

| Gate | Threshold | Result | Status |
|------|-----------|--------|--------|
| Champion mean score | ≥ 0.88 | 0.905 | **PASS** |
| Approval rate | ≥ 60% | 66.7% | **PASS** |
| All 6 campaigns complete | 6/6 | 6/6 | **PASS** |
| All 12 labels collected | 12/12 | 12/12 | **PASS** |
| All integrity checks pass | integrity_ok | 6/6 ok | **PASS** |

**Baseline ready: YES**

---

## Timing

| Phase | Start | End | Duration |
|-------|-------|-----|----------|
| Eval batch (3 runs) | 16:08:26 | 17:15:01 | 66m 35s |
| Production batch (3 runs) | 17:15:10 | 20:22:55 | 3h 7m 45s |
| Total batch | 16:08:26 | 20:22:55 | 4h 14m 29s |

---

## Artifact Index

| Artifact | Path |
|----------|------|
| This document | `runtime/phase9c/daily_collection/batch_summary.md` |
| Batch summary JSON | `runtime/phase9c/daily_collection/batch_summary.json` |
| Champions CSV | `runtime/phase9c/daily_collection/champions.csv` |
| Campaign metrics CSV | `runtime/phase9c/daily_collection/campaign_metrics.csv` |
| Review labels CSV | `runtime/phase9c/daily_collection/review_labels.csv` |
| Label completeness JSON | `runtime/phase9c/daily_collection/label_completeness_summary.json` |
| Full collection summary | `runtime/phase9c/daily_collection/daily_collection_summary.json` |
| Regime 2 baseline JSON | `runtime/baselines/phase9c_operational_baseline_regime2.json` |
| Phase 9D readiness doc | `docs/BREAKTHROUGH_ENGINE_PHASE9D_READY.md` |
