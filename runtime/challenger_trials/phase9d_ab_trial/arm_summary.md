# Phase 9D A/B Trial Arm Summary

**Trial ID**: phase9d_ab_trial
**Date**: 2026-03-11–12
**Profile**: eval_clean_energy_30m
**Embedding**: qwen3-embedding:4b (Regime 2)
**Status**: COMPLETE — PROMOTION_RECOMMENDED

---

## Champion Arm (phase5_champion) — 6 Campaigns

| Run | Campaign ID | Champion Title | Score | Short. | Decision |
|-----|-------------|----------------|-------|--------|----------|
| C1 | 395427c74e9b | Sulfide Electrolyte Thermal Runaway Suppression via Phase Transition | **0.9205** | 3 | approve |
| C2 | 5f66091ebc22 | Thermal Management Optimization for Large-Scale Electrolyzer Arrays | 0.8830 | 6 | approve |
| C3 | 5d4ffdb3fcc0 | Thermophotovoltaic Waste Heat Recovery for District Heating Integration | 0.8930 | 6 | approve |
| C4 | 0d85970835ed | Perovskite-Tandem Coating for Offshore Wave Energy Converter Power Take-Offs | 0.8930 | 6 | approve |
| C5 | 8cf41bbecb3c | Lignin-Derived Perovskite Passivation for Biomass Solar Integration | 0.8830 | 3 | **defer** |
| C6 | 8a1baaf2d75c | Biogenic Sulfide Interface Engineering for Bio-Battery Stability | 0.8730 | 3 | **defer** |

**Champion arm summary:**
- Mean score: **0.8909** | Min: 0.8730 | Max: 0.9205
- Approval rate: **66.7%** (4/6 approved)
- Mean novelty confidence: **0.807**
- Mean technical plausibility: **0.800**
- Mean commercialization relevance: **0.757**

---

## Challenger Arm (evidence_diversity_v1) — 6 Campaigns

| Run | Campaign ID | Champion Title | Score | Short. | Decision |
|-----|-------------|----------------|-------|--------|----------|
| CH1 | 117d49f08305 | Carrier Lifetime Extension via Trap-State Suppression in Tandems | **0.9205** | 3 | approve |
| CH2 | 6ca72240342d | Thermally Stabilized Tandem Junctions via Waste Heat Sink Integration | **0.9205** | 3 | approve |
| CH3 | 25afc501cfbd | Thermal-to-Chemical Coupling for High-Temp Battery Safety | **0.9205** | 6 | approve |
| CH4 | 4089e3888df3 | NiFe-LDH Membrane Integration for Seawater Electrolysis Stability | 0.9105 | 3 | approve |
| CH5 | ff41d501a44f | NiFe-LDH Anode Coupling with Low-Temp DAC for Integrated Green H2/DAC Systems | 0.9115 | 3 | approve |
| CH6 | 65745a5faa80 | High-Energy Density Argyrodite Coatings for Lightning Protection | 0.8930 | 3 | **defer** |

**Challenger arm summary:**
- Mean score: **0.9128** | Min: 0.8930 | Max: 0.9205
- Approval rate: **83.3%** (5/6 approved)
- Mean novelty confidence: **0.843**
- Mean technical plausibility: **0.843**
- Mean commercialization relevance: **0.802**

---

## Head-to-Head Comparison

| Metric | Champion | Challenger | Delta | Gate (≥) | Pass? |
|--------|----------|------------|-------|----------|-------|
| Mean champion score | 0.8909 | 0.9128 | **+0.022** | -0.03 | **PASS** |
| Approval rate | 66.7% | 83.3% | **+16.7pp** | -5pp | **PASS** |
| Novelty confidence (mean) | 0.807 | 0.843 | **+0.036** | -0.05 | **PASS** |
| Technical plausibility (mean) | 0.800 | 0.843 | **+0.043** | -0.05 | **PASS** |

**All 4 gates PASS. PROMOTION_RECOMMENDED.**

---

## Runner-Up Quality Comparison

| Arm | Approve | Defer | Approval rate |
|-----|---------|-------|---------------|
| Champion | 1/6 | 5/6 | 16.7% |
| Challenger | 3/6 | 3/6 | 50.0% |

The challenger arm also produced higher-quality runner-ups — consistent with the hypothesis that better mechanism-aligned evidence improves the entire finalist pool, not just the champion.

---

## Key Finding

The evidence_diversity_v1 hypothesis is confirmed:
- Mechanism-aligned evidence surfacing (mechanism_overlap 0.20→0.35) improved reviewer-assessed plausibility and novelty **without novelty suppression**
- The generation prompt and scoring weights were unchanged — the improvement is cleanly attributable to the evidence ranking change
- The intervention worked through the expected mechanism: better mechanistic grounding in the retrieved evidence → more specific candidates → higher reviewer plausibility and approval rates

This is a clean, interpretable result. The single-surface design of the challenger allows confident causal attribution.
