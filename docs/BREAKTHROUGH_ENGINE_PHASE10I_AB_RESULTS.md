# Phase 10I: Confirmatory Retrieval A/B Results

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

## Changes from Phase 10H

1. `select_diverse_top_k()` replaces naive top-k in evidence pack construction
2. Fresh `EvidenceItem` IDs per pack prevent INSERT OR REPLACE collisions
3. A/B script tracks `packs_with_items`, `total_packs`, `persistence_rate`

## Results

### Current Arm (ExistingFindingsSource + Semantic Scholar)

| Campaign | Champion Score | Finalists | Sources | Persistence | Champion |
|----------|--------------|-----------|---------|-------------|---------|
| 1 | 0.8755 | 6 | 2 | 7/7 | Corrosion-Resistant HEO Coatings |
| 2 | 0.9230 | 8 | 2 | 8/8 | Gradient-Resistant HEA/Graphene Aerogel Membranes |
| 3 | 0.8855 | 6 | 2 | 7/7 | Quantum-Simulated Single-Atom Catalysts |
| 4 | 0.9230 | 7 | 2 | 7/7 | Quantum-Simulated Band Convergence |
| 5 | 0.8847 | 6 | 2 | 8/8 | Graded HEA Thermal Interfaces |
| 6 | 0.9330 | 7 | 2 | 7/7 | Defect-Tolerant CO2 Reduction |
| 7 | 0.8855 | 6 | 2 | 7/7 | Single-Atom CO2 Reduction Catalysts |
| **Mean** | **0.9015** | **6.6** | **2.0** | **100%** | |

### Graph-Native Arm (HybridKGEvidenceSource)

| Campaign | Champion Score | Finalists | Sources | Persistence | Champion |
|----------|--------------|-----------|---------|-------------|---------|
| 1 | 0.9230 | 7 | 1 | 7/7 | High-Entropy Alloy Current Collectors |
| 2 | 0.9230 | 6 | 1 | 7/7 | HEA Grain-Boundary Engineering |
| 3 | 0.8855 | 6 | 1 | 7/7 | MXene-Reinforced ZIF-8 Membranes |
| 4 | 0.9230 | 7 | 1 | 7/7 | Self-Healing MOF-Membrane Interfaces |
| 5 | 0.9230 | 7 | 1 | 7/7 | Directional Thermal Aerogel Panels |
| 6 | 0.9230 | 7 | 1 | 7/7 | MXene-PV Tandem Facades |
| 7 | 0.9330 | 6 | 1 | 7/7 | High-Entropy Alloy Reinforced Self-Healing Elastomers |
| **Mean** | **0.9191** | **6.6** | **1.0** | **100%** | |

### Comparison

| Metric | Current | Graph Native | Delta |
|--------|---------|-------------|-------|
| Mean champion score | 0.9015 | **0.9191** | **+0.0176** |
| Min champion score | 0.8755 | 0.8855 | +0.0100 |
| Max champion score | 0.9330 | 0.9330 | 0 |
| Approval rate | 100% | 100% | 0 |
| Mean unique sources | 2.0 | 1.0 | -1.0 |
| Persistence rate | 100% | 100% | 0 |
| Mean elapsed (s) | 941.7 | 944.8 | +0.3% |

## Threshold Checks

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| Score preservation (>= -0.01) | -0.01 | +0.0176 | **PASS** |
| Score above rollback (>= -0.05) | -0.05 | +0.0176 | **PASS** |
| Approval >= 60% | 60% | 100% | **PASS** |
| Approval above rollback (>= 40%) | 40% | 100% | **PASS** |
| Diversity >= current | >= 2.0 | 1.0 | **FAIL** |
| No systematic failures | <= 1 | 0 | **PASS** |

## Review Labels

- Total: 28 (14 per arm)
- Approve: 28 (100%)
- Defer: 0
- Reject: 0
- Completeness: all_campaigns_labeled

## Phase-over-Phase Comparison

| Metric | Phase 10G | Phase 10H | Phase 10I |
|--------|-----------|-----------|-----------|
| Campaigns per arm | 6 | 7 | 7 |
| Score delta | +0.004 | +0.0014 | **+0.0176** |
| Approval | 100%/100% | 100%/100% | 100%/100% |
| Diversity check | FAIL | FAIL | FAIL |
| Ranking fix | None | None | diversity_aware_v1 |
| Persistence fix | None | None | fresh_ids_per_pack |
| Persistence rate | ~14% | ~14% | **100%** |
| Graph caching | No | Yes | Yes |

## Interpretation

The +0.0176 score advantage is the strongest observed across three phases of
A/B testing. The persistence fix (100% vs ~14%) is confirmed working. The
diversity-aware ranking maintains source diversity for the current arm
(unique_sources=2.0) but cannot create diversity that doesn't exist in the
graph-native evidence pool.
