# Phase 10K: Graph-Native Retrieval Production Burn-in Results

**Date:** 2026-03-14
**Branch:** `breakthrough-engine-phase10k-graph-native-rollout`

## Configuration

| Parameter | Value |
|-----------|-------|
| Campaigns | 6 (3 evaluation + 3 production) |
| Retrieval | HybridKGEvidenceSource (graph-native) |
| Policy | evidence_diversity_v1 (fixed) |
| Embedding | qwen3-embedding:4b (Regime 2) |
| Generation | qwen3.5:9b-q4_K_M |
| Mode | production_shadow |
| Graph context | enabled |
| evidence_refs fix | diversity_fallthrough_v1 (Phase 10J) |
| Pool construction | source_aware_v1 (Phase 10J) |

## Campaign Results

### Evaluation Campaigns

| # | Champion | Score | Finalists | Sources | Diversity | Persistence |
|---|---------|-------|-----------|---------|-----------|-------------|
| 1 | HEA-Based Thermal Conductivity Gradients | 0.8955 | 7 | 11 | 0.786 | 7/7 |
| 2 | NiFe-LDH Anode Integration into ZIF-8 MOF Reactors | 0.8855 | 7 | 9 | 0.643 | 7/7 |
| 3 | MXene-MOF Membrane Hybrids for Isotope-Specific H2 | 0.923 | 7 | 10 | 0.714 | 7/7 |

### Production Campaigns

| # | Champion | Score | Finalists | Sources | Diversity | Persistence |
|---|---------|-------|-----------|---------|-----------|-------------|
| 1 | Topological Insulator Spin-Logic for Smart Grid | 0.8955 | 7 | 8 | 0.571 | 7/7 |
| 2 | Ultrafast Ionic Transport for Dehumidified Insulation | 0.9324 | 4 | 5 | 0.455 | 7/7 |
| 3 | Ultrafast Ion Transport Sensors for Corrosion Monitoring | 0.933 | 6 | 11 | 0.786 | 7/7 |

## Burn-in vs Prior Baseline

| Metric | Prior Baseline | Burn-in | Delta |
|--------|---------------|---------|-------|
| Mean champion score | 0.9126 | 0.9108 | -0.0018 |
| Approval rate | 83.3% | 100% | +16.7% |
| Mean unique sources | 2.0 | 9.0 | +7.0 |
| Mean diversity score | — | 0.659 | — |
| Mean top concentration | — | 26.9% | — |
| Persistence rate | — | 100% | — |
| Mean elapsed (s) | — | 891 | — |

## Health Checks

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| Score preserved (>= -0.01) | -0.01 | -0.0018 | **PASS** |
| Score above rollback (>= -0.05) | -0.05 | -0.0018 | **PASS** |
| Approval >= 60% | 60% | 100% | **PASS** |
| Approval above rollback (>= 40%) | 40% | 100% | **PASS** |
| No systematic failures | <= 1 | 0 | **PASS** |
| Persistence OK (>= 90%) | 90% | 100% | **PASS** |

## Review Labels

- Total: 12 (6 champions + 6 runner-ups)
- Approve: 12 (100%)
- Defer: 0
- Reject: 0
- Completeness: all_campaigns_labeled

## Recommendation

**`ready_to_merge_and_adopt`** — All 6 health checks pass. Graph-native retrieval
holds up in production-like use with dramatically improved evidence diversity.
