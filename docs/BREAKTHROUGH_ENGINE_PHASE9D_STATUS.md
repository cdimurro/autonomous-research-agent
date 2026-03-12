# Phase 9D Status

**Phase**: 9D — evidence_diversity_v1 A/B Trial
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Commit at start**: `52561de`
**Date**: 2026-03-11

---

## Current State

| Item | Status |
|------|--------|
| Phase A: Readiness doc / naming cleanup | COMPLETE |
| Phase B: Comparability check | COMPLETE — comparability_ok=true |
| Phase C: 6+6 A/B batch | **COMPLETE** — 12/12 campaigns, all completed_with_draft |
| Phase D: Review label collection | **COMPLETE** — 24/24 labels |
| Phase E: Posterior update | **COMPLETE** |
| Phase F: Promotion decision | **COMPLETE — PROMOTION_RECOMMENDED** |
| Phase G: Daily automation confirmation | CONFIRMED |
| Tests | 864 passing, 0 failures (no code changes this phase) |

---

## Runtime State

| Parameter | Value |
|-----------|-------|
| Branch | `breakthrough-engine-phase9c-challenger-iteration` |
| Commit | `52561de` |
| Champion policy | `phase5_champion` |
| Challenger policy | `evidence_diversity_v1` (id=3f24a0a2a8074759) |
| Embedding model | `qwen3-embedding:4b` (Regime 2, 2560d) |
| Evaluation profile | `eval_clean_energy_30m` |
| Trial ID | `phase9d_ab_trial` |
| Operational baseline | `phase9c_operational_baseline_regime2` |

---

## Phase A: Readiness Doc / Naming Cleanup

| Fix | Status |
|-----|--------|
| Prerequisites: all marked COMPLETE | DONE |
| Trial ID: phase9c_ab_trial → phase9d_ab_trial | DONE |
| Baseline values refreshed from frozen baseline | DONE |
| CHALLENGER_V2_DESIGN.md: trial ID fixed | DONE |
| Artifact path: phase9d_ab_trial/ | DONE |

---

## Phase B: Comparability Check

| Check | Result |
|-------|--------|
| qwen3-embedding:4b confirmed active | PASS |
| Champion arm dry-run | PASS |
| Challenger arm dry-run | PASS ("Policy override: evidence_diversity_v1") |
| Both use eval_clean_energy_30m | CONFIRMED |
| Same embedding regime | CONFIRMED |
| **comparability_ok** | **TRUE** |

---

## Phase C: 6+6 A/B Batch

### Campaign Launch Configuration

```bash
# Champion arm (×6)
BT_EMBEDDING_MODEL=qwen3-embedding:4b \
  .venv/bin/python -m breakthrough_engine campaign run --profile eval_clean_energy_30m

# Challenger arm (×6)
BT_EMBEDDING_MODEL=qwen3-embedding:4b \
  .venv/bin/python -m breakthrough_engine campaign run --profile eval_clean_energy_30m \
  --policy evidence_diversity_v1
```

### Champion Arm — COMPLETE

| Run | Campaign ID | Champion Title | Score | Decision |
|-----|-------------|----------------|-------|----------|
| C1 | 395427c74e9b | Sulfide Electrolyte Thermal Runaway Suppression via Phase Transition | 0.9205 | approve |
| C2 | 5f66091ebc22 | Thermal Management Optimization for Large-Scale Electrolyzer Arrays | 0.8830 | approve |
| C3 | 5d4ffdb3fcc0 | Thermophotovoltaic Waste Heat Recovery for District Heating Integration | 0.8930 | approve |
| C4 | 0d85970835ed | Perovskite-Tandem Coating for Offshore Wave Energy Converter Power Take-Offs | 0.8930 | approve |
| C5 | 8cf41bbecb3c | Lignin-Derived Perovskite Passivation for Biomass Solar Integration | 0.8830 | defer |
| C6 | 8a1baaf2d75c | Biogenic Sulfide Interface Engineering for Bio-Battery Stability | 0.8730 | defer |

**Mean: 0.8909 | Approval rate: 66.7%**

### Challenger Arm — COMPLETE

| Run | Campaign ID | Champion Title | Score | Decision |
|-----|-------------|----------------|-------|----------|
| CH1 | 117d49f08305 | Carrier Lifetime Extension via Trap-State Suppression in Tandems | 0.9205 | approve |
| CH2 | 6ca72240342d | Thermally Stabilized Tandem Junctions via Waste Heat Sink Integration | 0.9205 | approve |
| CH3 | 25afc501cfbd | Thermal-to-Chemical Coupling for High-Temp Battery Safety | 0.9205 | approve |
| CH4 | 4089e3888df3 | NiFe-LDH Membrane Integration for Seawater Electrolysis Stability | 0.9105 | approve |
| CH5 | ff41d501a44f | NiFe-LDH Anode Coupling with Low-Temp DAC for Integrated Green H2/DAC Systems | 0.9115 | approve |
| CH6 | 65745a5faa80 | High-Energy Density Argyrodite Coatings for Lightning Protection | 0.8930 | defer |

**Mean: 0.9128 | Approval rate: 83.3%**

### Promotion Decision: PROMOTION_RECOMMENDED

All 4 gates pass. See `docs/BREAKTHROUGH_ENGINE_PHASE9D_PROMOTION_DECISION.md`.

---

## Phase G: Daily Automation Confirmation

Production automation remains champion-only. evidence_diversity_v1 is NOT enabled in
any production profile. It can only be invoked explicitly via `--policy evidence_diversity_v1`.

The trial runs under `campaign run` (not `daily run`), so there is no interaction with
the daily automation system's max-runs-per-day guard.

---

## Artifact Locations

| Artifact | Path |
|----------|------|
| Trial config | `runtime/challenger_trials/phase9d_ab_trial/trial_config.json` |
| Arm summary | `runtime/challenger_trials/phase9d_ab_trial/arm_summary.json` |
| Champions CSV | `runtime/challenger_trials/phase9d_ab_trial/champions.csv` |
| Review labels | `runtime/challenger_trials/phase9d_ab_trial/review_labels.csv` |
| Posterior summary | `runtime/challenger_trials/phase9d_ab_trial/posterior_summary.json` |
| Phase 9D results | `docs/BREAKTHROUGH_ENGINE_PHASE9D_RESULTS.md` |
| Promotion decision | `docs/BREAKTHROUGH_ENGINE_PHASE9D_PROMOTION_DECISION.md` |
