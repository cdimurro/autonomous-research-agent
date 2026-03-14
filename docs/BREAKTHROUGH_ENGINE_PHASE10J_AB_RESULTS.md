# Phase 10J: Confirmatory Retrieval A/B Results

**Date:** 2026-03-14
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`

## Experiment Configuration

| Parameter | Value |
|-----------|-------|
| Campaigns per arm | 7 |
| Policy | evidence_diversity_v1 (fixed) |
| Embedding | qwen3-embedding:4b (Regime 2) |
| Generation | qwen3.5:9b-q4_K_M |
| Mode | production_shadow |
| Domain | clean-energy + materials |
| Ranking | diversity_aware_v1 (Phase 10I) |
| Persistence | fresh_ids_per_pack (Phase 10I) |
| Graph caching | enabled |
| Evidence_refs fix | diversity_fallthrough_v1 (Phase 10J) |
| Pool construction | source_aware_v1 (Phase 10J) |

## Changes from Phase 10I

1. **Evidence_refs diversity check** (orchestrator.py): When matched items have
   fewer unique sources than top_k, fall through to ranked matching so
   `select_diverse_top_k()` can enforce source diversity.
2. **Source-aware hybrid pool** (hybrid_retrieval.py): KG items guaranteed in
   pool via `min_kg_items=2` slot reservation; `max_per_paper=3` cap prevents
   any single paper from dominating. `_select_diverse_kg()` prefers items from
   distinct sources.
3. Prior fixes preserved: diversity-aware ranking + persistence fix from Phase 10I.

## Results

### Current Arm (ExistingFindingsSource + Semantic Scholar)

| Campaign | Champion Score | Finalists | Sources | Persistence | Champion |
|----------|--------------|-----------|---------|-------------|---------|
| 1 | 0.8955 | 6 | 2 | 6/6 | 3D-Printed Gradient Porosity Structures |
| 2 | 0.8855 | 7 | 2 | 7/7 | High-Ductility HEA Wind Turbine Blades |
| 3 | 0.8855 | 6 | 2 | 6/6 | Quantum-Simulated Cryogenic Insulation |
| 4 | 0.9330 | 7 | 2 | 7/7 | Bio-polymer Encapsulated High-Entropy Alloys |
| 5 | 0.9230 | 5 | 2 | 7/7 | Hybrid Perovskite-HEA Radiators |
| 6 | 0.9230 | 7 | 2 | 8/8 | Self-Healing Single-Atom Catalysts |
| 7 | 0.8955 | 7 | 2 | 7/7 | 3D-Printed Gradient HEA Electrodes |
| **Mean** | **0.9059** | **6.4** | **2.0** | **100%** | |

### Graph-Native Arm (HybridKGEvidenceSource)

| Campaign | Champion Score | Finalists | Sources | Persistence | Champion |
|----------|--------------|-----------|---------|-------------|---------|
| 1 | 0.8938 | 7 | 10 | 7/7 | MXene-Based Proton Sieving |
| 2 | 0.9230 | 7 | 10 | 7/7 | MXene-Modified Polymer Nanocomposites |
| 3 | 0.9230 | 7 | 7 | 7/7 | MXene-Enabled Ionic Selectivity |
| 4 | 0.9330 | 7 | 9 | 7/7 | Self-Healing Aerogel-MXene Interfaces |
| 5 | 0.9330 | 7 | 8 | 7/7 | Spin-Orbit Torque-Assisted Charge Separation |
| 6 | 0.9230 | 7 | 11 | 8/8 | MXene-Enabled Directional Heat Spreading |
| 7 | 0.8855 | 7 | 6 | 7/7 | HEA Microstructure Mimicry in Sulfide Electrolytes |
| **Mean** | **0.9163** | **7.0** | **8.7** | **100%** | |

### Comparison

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean champion score | 0.9059 | **0.9163** | **+0.0104** |
| Min champion score | 0.8855 | 0.8855 | 0 |
| Max champion score | 0.9330 | 0.9330 | 0 |
| Approval rate | 100% | 100% | 0 |
| Mean unique sources | 2.0 | **8.7** | **+6.7** |
| Mean diversity score | 0.147 | **0.608** | **+0.461** |
| Mean top concentration | 50.0% | **22.2%** | **-27.8%** |
| Persistence rate | 100% | 100% | 0 |
| Mean elapsed (s) | 927.5 | 950.1 | +2.4% |

## Threshold Checks

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| Score preservation (>= -0.01) | -0.01 | +0.0104 | **PASS** |
| Score above rollback (>= -0.05) | -0.05 | +0.0104 | **PASS** |
| Approval >= 60% | 60% | 100% | **PASS** |
| Approval above rollback (>= 40%) | 40% | 100% | **PASS** |
| Diversity >= current | >= 2.0 | 8.7 | **PASS** |
| No systematic failures | <= 1 | 0 | **PASS** |

## Review Labels

- Total: 28 (14 per arm)
- Approve: 28 (100%)
- Defer: 0
- Reject: 0
- Completeness: all_campaigns_labeled

## Phase-over-Phase Comparison

| Metric | Phase 10G | Phase 10H | Phase 10I | Phase 10J |
|--------|-----------|-----------|-----------|-----------|
| Campaigns per arm | 6 | 7 | 7 | 7 |
| Score delta | +0.004 | +0.0014 | +0.0176 | **+0.0104** |
| Approval | 100%/100% | 100%/100% | 100%/100% | 100%/100% |
| Diversity check | FAIL | FAIL | FAIL | **PASS** |
| Graph-native sources | 1.0 | 1.0 | 1.0 | **8.7** |
| Persistence rate | ~14% | ~14% | 100% | 100% |
| All checks pass | No | No | No | **Yes** |

## Root Cause Resolution

| Phase | Diversity Failure Layer | Fix |
|-------|----------------------|-----|
| 10G | Measurement (paper-level source_ids) | — |
| 10H | Ranking (top-k concentrates on one source) | segment-level source_ids |
| 10I | Evidence pool (KG corpus dominated by one paper) | diversity-aware ranking + persistence |
| **10J** | **evidence_refs bypass + pool construction** | **diversity fallthrough + source-aware pool** |

The evidence_refs bypass was the true root cause: the generator sets `evidence_refs`
on ALL candidates, causing the orchestrator to match items directly and completely
skip `rank_evidence()` + `select_diverse_top_k()`. For graph-conditioned candidates,
all refs pointed to items from a single paper. The Phase 10J diversity check detects
this monoculture and falls through to the ranked path, where the diversity-aware
ranking enforces source diversity.

## Recommendation

**`promote_graph_native_retrieval`** — All 6 threshold checks pass for the first
time across four phases of A/B testing.
