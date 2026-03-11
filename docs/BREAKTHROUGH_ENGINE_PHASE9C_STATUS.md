# Phase 9C Status

**Phase**: 9C — Champion Lock, Challenger Iteration, Daily Collection
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Base**: `ae1908b` (Phase 9B complete)
**Date**: 2026-03-11

---

## Current State Summary

| Item | Status |
|------|--------|
| Phase 9B trial frozen | COMPLETE — PROMOTION_NOT_RECOMMENDED |
| Champion | `phase5_champion` (locked) |
| Failed challenger | `synthesis_focus_v1` (RETIRED_FAILED) |
| Challenger v2 | `evidence_diversity_v1` (REGISTERED, not yet trialed) |
| Daily collection | SCAFFOLD READY — batch pending Ollama availability |
| Proof of actuation | COMPLETE — deterministic ranking difference verified |
| Tests | 779 passing (Phase 9B base) + Phase 9C tests added |
| Branch | `breakthrough-engine-phase9c-challenger-iteration` |

---

## Champion Production Lock

**Current champion**: `phase5_champion`
**Scoring weights**: standard (novelty 0.20, plausibility 0.20, impact 0.20, evidence_strength 0.20, sim_readiness 0.10, inv_validation_cost 0.10)
**Generation prompt**: standard
**Evidence ranking**: program defaults (api_relevance 0.35, domain_overlap 0.30, mechanism_overlap 0.20, baseline 0.15)

**Automatic promotion**: OFF
**Challenger leakage into production**: IMPOSSIBLE (daily automation profiles use no `--policy` flag; default is always champion)

**Production commands**:
```bash
python -m breakthrough_engine daily run evaluation_daily_clean_energy
python -m breakthrough_engine daily run production_daily_clean_energy
```

---

## Phase 9B Trial Outcome (Frozen)

| Metric | Champion | Challenger | Delta |
|--------|----------|------------|-------|
| Mean score | 0.90804 | 0.87789 | -0.030 |
| Approval rate | 75% | 25% | -50pp |
| Novelty confidence | 0.783 | 0.713 | -0.070 |
| Technical plausibility | 0.763 | 0.694 | -0.069 |
| Commercialization | 0.710 | 0.633 | -0.077 |

**Verdict**: PROMOTION_NOT_RECOMMENDED
**Root cause**: scoring weights are selection tools, not quality levers; synthesis_focus prompt suppressed novelty without compensating plausibility gains.

---

## Challenger V2 (evidence_diversity_v1)

**Design**: Single surface change — `evidence_ranking_weights`
**Change**: mechanism_overlap 0.20→0.35 (+75%), api_relevance 0.35→0.20 (-43%)
**Hypothesis**: Mechanism-aligned evidence selection leads to more specific, grounded candidates without suppressing novelty
**Status**: REGISTERED — config at `config/policies/evidence_diversity_v1.json`
**Proof of actuation**: Verified — different ranking on controlled evidence set

---

## Daily Collection (Phase 9C)

**Status**: Scaffold ready. Batch pending Ollama availability.

Collection target:
- 3 evaluation_daily_clean_energy runs (champion-only)
- 3 production_daily_clean_energy runs (champion-only)
- 2 review labels per campaign (champion + runner-up)

Artifacts: `runtime/phase9c/daily_collection/`

---

## Next Steps (Phase 9D)

1. Run Phase 9C daily collection batch when Ollama available
2. Collect and record review labels
3. Freeze new champion baseline from Phase 9C collection
4. Run 6+6 A/B batch (champion vs evidence_diversity_v1)
5. Collect 24+ review labels
6. Manual promotion decision

---

## Git History (Phase 9C)

```
breakthrough-engine-phase9c-challenger-iteration
├── Phase 9C: champion lock, evidence_diversity_v1 challenger, proof of actuation
└── base: ae1908b (Phase 9B: 6+6 Regime 2 A/B trial complete, PROMOTION_NOT_RECOMMENDED)
```

---

## Key File Locations

| Item | Path |
|------|------|
| Phase 9C plan | `docs/BREAKTHROUGH_ENGINE_PHASE9C_PLAN.md` |
| Failure analysis | `docs/BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md` |
| Challenger v2 design | `docs/BREAKTHROUGH_ENGINE_CHALLENGER_V2_DESIGN.md` |
| Daily collection plan | `docs/BREAKTHROUGH_ENGINE_PHASE9C_DAILY_COLLECTION.md` |
| Challenger v2 policy | `config/policies/evidence_diversity_v1.json` |
| Frozen arm summary | `runtime/challenger_trials/phase9b_ab_trial/arm_summary.json` |
| Proof of actuation | `runtime/phase9c/proof_of_actuation/` |
| Daily collection scaffold | `runtime/phase9c/daily_collection/` |
| Phase 9C tests | `tests/test_breakthrough/test_phase9c.py` |
