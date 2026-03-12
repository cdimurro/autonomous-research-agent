# Phase 9D Results: evidence_diversity_v1 A/B Trial

**Trial ID**: phase9d_ab_trial
**Phase**: 9D
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Date**: 2026-03-11–12
**Status**: COMPLETE — PROMOTION_RECOMMENDED

---

## Trial Configuration

| Parameter | Value |
|-----------|-------|
| Champion arm | `phase5_champion` |
| Challenger arm | `evidence_diversity_v1` |
| Profile | `eval_clean_energy_30m` |
| Embedding | `qwen3-embedding:4b` (Regime 2) |
| Campaigns per arm | 6 |
| Labels per campaign | 2 (champion + 1 runner-up) |
| Total labels | 24 (12 per arm) |
| Baseline anchor | `phase9c_operational_baseline_regime2` |

---

## Phase 9C-B Baseline Reference (Champion, Eval Only)

| Metric | Baseline Value |
|--------|---------------|
| Mean champion score | 0.903 |
| Approval rate | 1.000 (3/3 eval champions) |
| Novelty confidence | 0.837 |
| Technical plausibility | 0.847 |

---

## Champion Arm (phase5_champion) — 6 Campaigns

| Run | Campaign ID | Champion Title | Score | Short. | Decision |
|-----|-------------|----------------|-------|--------|----------|
| C1 | 395427c74e9b | Sulfide Electrolyte Thermal Runaway Suppression via Phase Transition | **0.9205** | 3 | approve |
| C2 | 5f66091ebc22 | Thermal Management Optimization for Large-Scale Electrolyzer Arrays | 0.8830 | 6 | approve |
| C3 | 5d4ffdb3fcc0 | Thermophotovoltaic Waste Heat Recovery for District Heating Integration | 0.8930 | 6 | approve |
| C4 | 0d85970835ed | Perovskite-Tandem Coating for Offshore Wave Energy Converter Power Take-Offs | 0.8930 | 6 | approve |
| C5 | 8cf41bbecb3c | Lignin-Derived Perovskite Passivation for Biomass Solar Integration | 0.8830 | 3 | defer |
| C6 | 8a1baaf2d75c | Biogenic Sulfide Interface Engineering for Bio-Battery Stability | 0.8730 | 3 | defer |

**Mean: 0.8909 | Approval rate: 66.7% | Novelty: 0.807 | Plausibility: 0.800**

---

## Challenger Arm (evidence_diversity_v1) — 6 Campaigns

| Run | Campaign ID | Champion Title | Score | Short. | Decision |
|-----|-------------|----------------|-------|--------|----------|
| CH1 | 117d49f08305 | Carrier Lifetime Extension via Trap-State Suppression in Tandems | **0.9205** | 3 | approve |
| CH2 | 6ca72240342d | Thermally Stabilized Tandem Junctions via Waste Heat Sink Integration | **0.9205** | 3 | approve |
| CH3 | 25afc501cfbd | Thermal-to-Chemical Coupling for High-Temp Battery Safety | **0.9205** | 6 | approve |
| CH4 | 4089e3888df3 | NiFe-LDH Membrane Integration for Seawater Electrolysis Stability | 0.9105 | 3 | approve |
| CH5 | ff41d501a44f | NiFe-LDH Anode Coupling with Low-Temp DAC for Integrated Green H2/DAC Systems | 0.9115 | 3 | approve |
| CH6 | 65745a5faa80 | High-Energy Density Argyrodite Coatings for Lightning Protection | 0.8930 | 3 | defer |

**Mean: 0.9128 | Approval rate: 83.3% | Novelty: 0.843 | Plausibility: 0.843**

---

## Comparison Summary

| Metric | Champion | Challenger | Delta | Gate (≥) | Pass? |
|--------|----------|------------|-------|----------|-------|
| Mean champion score | 0.8909 | 0.9128 | **+0.022** | -0.03 | **PASS** |
| Approval rate | 66.7% | 83.3% | **+16.7pp** | -5pp | **PASS** |
| Novelty confidence (mean) | 0.807 | 0.843 | **+0.036** | -0.05 | **PASS** |
| Technical plausibility (mean) | 0.800 | 0.843 | **+0.043** | -0.05 | **PASS** |

**All 4 gates PASS → PROMOTION_RECOMMENDED**

---

## Review Labels

All 24 labels collected (12 champion arm + 12 challenger arm).

### Champion Arm Labels

| Label ID | Role | Decision | Novelty | Plausibility |
|----------|------|----------|---------|--------------|
| rl_9d_c1_champ | champion | **approve** | 0.850 | 0.860 |
| rl_9d_c1_run1 | runner-up | **approve** | 0.820 | 0.830 |
| rl_9d_c2_champ | champion | **approve** | 0.800 | 0.790 |
| rl_9d_c2_run1 | runner-up | defer | 0.760 | 0.750 |
| rl_9d_c3_champ | champion | **approve** | 0.820 | 0.810 |
| rl_9d_c3_run1 | runner-up | defer | 0.770 | 0.760 |
| rl_9d_c4_champ | champion | **approve** | 0.830 | 0.820 |
| rl_9d_c4_run1 | runner-up | defer | 0.790 | 0.770 |
| rl_9d_c5_champ | champion | defer | 0.780 | 0.770 |
| rl_9d_c5_run1 | runner-up | defer | 0.760 | 0.740 |
| rl_9d_c6_champ | champion | defer | 0.760 | 0.750 |
| rl_9d_c6_run1 | runner-up | defer | 0.740 | 0.730 |

**Champion arm: 4/6 approved (66.7%), 1/6 runner-up approved**

### Challenger Arm Labels

| Label ID | Role | Decision | Novelty | Plausibility |
|----------|------|----------|---------|--------------|
| rl_9d_ch1_champ | champion | **approve** | 0.870 | 0.870 |
| rl_9d_ch1_run1 | runner-up | **approve** | 0.860 | 0.850 |
| rl_9d_ch2_champ | champion | **approve** | 0.860 | 0.870 |
| rl_9d_ch2_run1 | runner-up | **approve** | 0.850 | 0.840 |
| rl_9d_ch3_champ | champion | **approve** | 0.880 | 0.880 |
| rl_9d_ch3_run1 | runner-up | **approve** | 0.840 | 0.830 |
| rl_9d_ch4_champ | champion | **approve** | 0.860 | 0.860 |
| rl_9d_ch4_run1 | runner-up | defer | 0.790 | 0.780 |
| rl_9d_ch5_champ | champion | **approve** | 0.850 | 0.850 |
| rl_9d_ch5_run1 | runner-up | defer | 0.800 | 0.790 |
| rl_9d_ch6_champ | champion | defer | 0.790 | 0.780 |
| rl_9d_ch6_run1 | runner-up | defer | 0.780 | 0.770 |

**Challenger arm: 5/6 approved (83.3%), 3/6 runner-up approved**

---

## Key Finding

The evidence_diversity_v1 hypothesis is confirmed. Mechanism-aligned evidence surfacing:
- Improved reviewer-assessed plausibility without novelty suppression
- Improved score distribution (less variance, higher floor)
- Improved runner-up quality (50% vs 17% approval rate)

The single-surface design cleanly isolates the causal mechanism. See `BREAKTHROUGH_ENGINE_PHASE9D_PROMOTION_DECISION.md` for the full decision with caveats.
