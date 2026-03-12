# Phase 9E Status

**Phase**: 9E
**Date**: 2026-03-12
**Status**: COMPLETE

---

## Current State

| Item | Value |
|------|-------|
| Branch | `breakthrough-engine-phase9c-challenger-iteration` |
| Commit | `ec715e4` (Phase 9D base) + Phase 9E artifacts |
| Tests | 864+ passing, 0 failures |
| Champion | `evidence_diversity_v1` (PROMOTED 2026-03-12T02:34:06Z) |
| Prior champion | `phase5_champion` (archived, rollback target) |
| Burn-in status | COMPLETE — 6/6 campaigns, 12/12 labels |
| Baseline status | FROZEN — `phase9e_promoted_production_baseline_regime2` |
| Rollback status | READY — command documented and verified |
| Embedding regime | Regime 2 (qwen3-embedding:4b) |

---

## Promotion Record

| Field | Value |
|-------|-------|
| Promoted policy | `evidence_diversity_v1` |
| Promoted at | 2026-03-12T02:34:06Z |
| Prior champion | `phase5_champion` |
| Trial evidence | `phase9d_ab_trial` (6+6 campaigns, all 4 gates pass) |
| Command used | `python -m breakthrough_engine policy manual-promote evidence_diversity_v1 --reason "..." --trial-id phase9d_ab_trial` |
| CLI fix included | Yes — `policy promote`/`rollback` tuple bug fixed; `manual-promote` command added |

---

## Burn-In Summary

| Metric | Burn-In (evidence_diversity_v1) | Phase 9C Baseline (phase5_champion) | Delta |
|--------|--------------------------------|-------------------------------------|-------|
| Mean score | 0.9126 | 0.905 | +0.008 |
| Approval rate | 83.3% | 66.7% | +16.7pp |
| Novelty | 0.853 | 0.837 | +0.016 |
| Plausibility | 0.855 | 0.847 | +0.008 |

**Verdict: BASELINE_HEALTHY**

---

## Schema and Environment

| Item | Value |
|------|-------|
| Embedding model | `qwen3-embedding:4b` (2560d, Regime 2) |
| Generation model | `qwen3.5:9b-q4_K_M` |
| Python | 3.14 |
| DB engine | SQLite (`runtime/bt_engine.db`, gitignored) |
| Pydantic | v2 |

---

## Active Challenger

**None.** No active challenger during burn-in. Next challenger prepared in design-only form (see `docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md`).

---

## Production Automation

| Profile | Status | Policy |
|---------|--------|--------|
| `evaluation_daily_clean_energy` | ACTIVE (champion-only) | `evidence_diversity_v1` |
| `production_daily_clean_energy` | ACTIVE (champion-only) | `evidence_diversity_v1` |

Commands:
```bash
python -m breakthrough_engine daily run evaluation_daily_clean_energy
python -m breakthrough_engine daily run production_daily_clean_energy
```

---

## Rollback Status

Rollback path is live and documented:
```bash
python -m breakthrough_engine policy rollback --reason "regression in Phase 9E burn-in"
```
This reverts to `phase5_champion`. See `docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md`.

---

## Baseline Registry

| Baseline ID | Policy | Regime | Status |
|------------|--------|--------|--------|
| phase5_validated_benchmark | phase5_champion | 1 | Archived |
| phase7d_reviewed_baseline | phase7d | 1 | Archived |
| phase8_reviewed_baseline | phase8 | 1 | Archived |
| phase9_new_embedding_reviewed | phase5_champion | 2 (early) | Archived |
| phase9c_operational_regime2 | phase5_champion | 2 | Prior anchor |
| **phase9e_promoted_production_regime2** | **evidence_diversity_v1** | **2** | **CURRENT** |

---

## Next Steps (Phase 10)

1. Design next challenger surface (see `docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md`)
2. Register challenger when ready
3. Run 6+6 A/B trial against `evidence_diversity_v1` as new baseline
4. Manual promotion decision
