# Phase 10K: Production Baseline — Graph-Native Retrieval

**Baseline ID:** `phase10k_graph_native_production_regime2`
**Date:** 2026-03-14
**Branch:** `breakthrough-engine-phase10k-graph-native-rollout`

## Overview

This baseline captures the first production burn-in under graph-native retrieval
(HybridKGEvidenceSource) as the default evidence source. It supersedes
`phase9e_promoted_production_regime2` for graph-native comparisons while the
prior baseline is retained as the rollback anchor.

## Configuration

| Parameter | Value |
|-----------|-------|
| Policy | evidence_diversity_v1 |
| Retrieval | HybridKGEvidenceSource |
| Embedding | qwen3-embedding:4b (Regime 2) |
| Generation | qwen3.5:9b-q4_K_M |
| Graph context | enabled |
| Phase 10J fixes | evidence_refs diversity fallthrough, source-aware hybrid pool |

## Metrics

| Metric | Value |
|--------|-------|
| Total campaigns | 6 (3 eval + 3 prod) |
| Mean champion score | 0.9108 |
| Min champion score | 0.8855 |
| Max champion score | 0.933 |
| Approval rate | 100% (12/12) |
| Mean unique sources | 9.0 |
| Mean diversity score | 0.659 |
| Mean top concentration | 26.9% |
| Persistence rate | 100% |

## Comparison vs Prior Baseline

| Metric | Phase 9E Baseline | Phase 10K Baseline | Delta |
|--------|------------------|-------------------|-------|
| Mean score | 0.9126 | 0.9108 | -0.0018 |
| Approval | 83.3% | 100% | +16.7% |
| Unique sources | 2.0 | 9.0 | +7.0 |

## Artifact Location

`runtime/baselines/phase10k_graph_native_production_baseline_regime2.json`

## Use For

- Graph-native retrieval production reference
- Future challenger comparisons under HybridKGEvidenceSource
- Regression detection after pipeline changes
- Merge-readiness evidence
