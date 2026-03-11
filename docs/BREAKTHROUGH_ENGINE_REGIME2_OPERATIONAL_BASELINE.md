# Regime 2 Operational Baseline

**Phase**: 9C-B
**Status**: COMPLETE — 6/6 campaigns, 12/12 labels, baseline_ready=true
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Date**: 2026-03-11

---

## Overview

This document tracks the Regime 2 (qwen3-embedding:4b) operational baseline for the
breakthrough engine champion policy (phase5_champion). It supersedes all Regime 1
(nomic-embed-text) baselines for policy comparison purposes.

---

## Baseline Hierarchy

| Baseline | Embedding Regime | Status | Use For |
|----------|-----------------|--------|---------|
| phase5_validated | Regime 1 (nomic-embed-text) | FROZEN | Historical reference only |
| phase7d_reviewed_oldregime | Regime 1 (nomic-embed-text) | FROZEN | Historical reference only |
| phase8_reviewed_oldregime | Regime 1 (nomic-embed-text) | FROZEN | Historical reference only |
| phase9_new_embedding_reviewed | Regime 2 (qwen3-embedding:4b) | FROZEN | Regime 2 entry point |
| phase9b_ab_trial (champion arm) | Regime 2 (qwen3-embedding:4b) | FROZEN | Phase 9B A/B champion anchor |
| **phase9c_operational_regime2** | **Regime 2 (qwen3-embedding:4b)** | **ACTIVE** | **Phase 9D A/B comparison** |

**CRITICAL**: Never compare Regime 1 baselines to Regime 2 results. The embedding dimension
change (768d → 2560d) makes novelty scores incomparable across regimes.

---

## Regime 2 Technical Configuration

| Parameter | Value |
|-----------|-------|
| Embedding model | `qwen3-embedding:4b` |
| Embedding dimensions | 2560 |
| Generation model | `qwen3.5:9b-q4_K_M` |
| Embedding provider | `OllamaEmbeddingProvider(qwen3-embedding:4b)` |
| Champion policy | `phase5_champion` |
| Scoring weights | standard (novelty 0.20, plausibility 0.20, impact 0.20, evidence_strength 0.20, sim_readiness 0.10, inv_validation_cost 0.10) |
| Boundary commit | `bbd7692` (Phase 9: full policy actuation) |

---

## Phase 9C-B Operational Baseline — Campaign Summary

### Evaluation Runs (eval_clean_energy_30m profile)

| Campaign ID | Champion Title | Score | Candidates | Shortlisted | Status |
|------------|----------------|-------|-----------|-------------|--------|
| 70b85ab1720a4859 | MOF-808 Insulation with Low-Temp Regeneration for Passive Building Cooling | 0.872 | 8 | 3 | completed_with_draft |
| efe33bd47e524534 | Quantum Dot BiVO4 Photocatalytic Desalination for Offshore Platforms | 0.921 | 8 | 3 | completed_with_draft |
| 4c5a48429f8c4469 | Quantum Dot-BiVO4 Sensitized Microalgae for Synergistic Bio-hydrogen | 0.917 | 15 | 6 | completed_with_draft |

**Evaluation mean champion score**: 0.903

### Production Runs (overnight_clean_energy profile)

| Campaign ID | Champion Title | Score | Candidates | Shortlisted | Status |
|------------|----------------|-------|-----------|-------------|--------|
| 983beee35a024e0d | Perovskite Tandem Trap Passivation via OABr Analogues | 0.8972 | 31 | 5 | completed_with_draft |
| a219f3a3f64b4e9a | Quantum dot-sensitized photo-electrochemical hydrogen generation in seawater | 0.8930 | 29 | 5 | completed_with_draft |
| 3886d50a5b3a4303 | Perovskite Solar Cell Tandem Stacking Increases Charge Collection Efficiency in Concentrated PV-Thermal Systems | 0.9305 | 29 | 5 | completed_with_draft |

**Production mean champion score**: 0.907

---

## Phase 9C-B Champion Quality Gates

**Phase 9C Daily Collection Quality Gates** (from BREAKTHROUGH_ENGINE_PHASE9C_DAILY_COLLECTION.md):

| Gate | Threshold | Result | Status |
|------|-----------|--------|--------|
| Champion mean score ≥ 0.88 | 0.88 | 0.905 (overall) | **PASS** |
| Approval rate ≥ 60% | 60% | 66.7% | **PASS** |
| All 6 campaigns complete | 6 | 6/6 | **PASS** |
| All 12 review labels collected | 12 | 12/12 | **PASS** |

---

## Relationship to Prior Baselines

### Why Regime 2 baselines differ from Regime 1

- `nomic-embed-text` (Regime 1): 768-dimensional embeddings. Used for novelty gating in Phases 1–8B.
- `qwen3-embedding:4b` (Regime 2): 2560-dimensional embeddings. Better representation quality,
  different cosine similarity space.

Novelty scores in Regime 2 are NOT directly comparable to Regime 1. This is expected and correct.
The Regime 2 scores are the new ground truth.

### Phase 9B Champion Arm vs Phase 9C-B

Phase 9B was the first Regime 2 A/B trial. The champion arm in Phase 9B used:
- Profile: `eval_clean_energy_30m`
- Policy: `phase5_champion`
- Embedding: `qwen3-embedding:4b`

Phase 9C-B extends this with 6 additional champion-only daily operation runs using both
`eval_clean_energy_30m` (evaluation profile) and `overnight_clean_energy` (production profile).

---

## When to Use This Baseline

Use `phase9c_operational_baseline_regime2` as the anchor for:
1. **Phase 9D A/B trial** (evidence_diversity_v1 vs phase5_champion)
2. **Future challenger trials** in Regime 2
3. **Regression detection** when any code change is made to the generation pipeline

Do NOT use Regime 1 baselines for any of these purposes.

---

## Artifact Locations

| Artifact | Path |
|----------|------|
| This document | `docs/BREAKTHROUGH_ENGINE_REGIME2_OPERATIONAL_BASELINE.md` |
| Baseline JSON | `runtime/baselines/phase9c_operational_baseline_regime2.json` |
| Campaign receipt DB | `runtime/db/scires.db` → `bt_campaign_receipts` |
| Review labels | `runtime/phase9c/daily_collection/review_labels.csv` |
| Batch summary | `runtime/phase9c/daily_collection/batch_summary.json` |
