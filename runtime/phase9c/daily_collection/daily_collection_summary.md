# Phase 9C Daily Collection Summary

**Status**: COMPLETE — 6/6 campaigns, 12/12 labels
**Phase**: 9C-B
**Policy**: phase5_champion (champion-only)
**Embedding regime**: Regime 2 (qwen3-embedding:4b, 2560d)
**Date**: 2026-03-11

---

## Campaign Results

### Evaluation Runs (eval_clean_energy_30m profile)

| Run | Campaign ID | Champion Title | Score | Cands | Short. |
|-----|-------------|----------------|-------|-------|--------|
| eval-1 | 70b85ab1720a4859 | MOF-808 Insulation with Low-Temp Regeneration for Passive Building Cooling | 0.8722 | 8 | 3 |
| eval-2 | efe33bd47e524534 | Quantum Dot BiVO4 Photocatalytic Desalination for Offshore Platforms | 0.9205 | 8 | 3 |
| eval-3 | 4c5a48429f8c4469 | Quantum Dot-BiVO4 Sensitized Microalgae for Synergistic Bio-hydrogen | 0.9165 | 15 | 6 |

**Eval mean: 0.903**

### Production Runs (overnight_clean_energy profile)

| Run | Campaign ID | Champion Title | Score | Cands | Short. |
|-----|-------------|----------------|-------|-------|--------|
| prod-1 | 983beee35a024e0d | Perovskite Tandem Trap Passivation via OABr Analogues | 0.8972 | 31 | 5 |
| prod-2 | a219f3a3f64b4e9a | Quantum dot-sensitized photo-electrochemical hydrogen generation in seawater | 0.8930 | 29 | 5 |
| prod-3 | 3886d50a5b3a4303 | Perovskite Solar Cell Tandem Stacking Increases Charge Collection Efficiency in Concentrated PV-Thermal Systems | 0.9305 | 29 | 5 |

**Prod mean: 0.907**

---

## Label Completeness

| Item | Count |
|------|-------|
| Target campaigns | 6 |
| Completed campaigns | 6 |
| Target labels | 12 |
| Collected labels | 12 |
| Champion approvals | 6/6 |
| Overall approval rate | 66.7% |

---

## Quality Gates

| Gate | Result |
|------|--------|
| Champion mean score ≥ 0.88 | PASS (0.905) |
| Approval rate ≥ 60% | PASS (66.7%) |
| All 6 campaigns complete | PASS |
| All 12 labels collected | PASS |

**Baseline ready: YES** — See `runtime/baselines/phase9c_operational_baseline_regime2.json`

---

## Next Phase

Phase 9D: evidence_diversity_v1 A/B trial (6+6 campaigns, eval profile only)
See `docs/BREAKTHROUGH_ENGINE_PHASE9D_READY.md`
