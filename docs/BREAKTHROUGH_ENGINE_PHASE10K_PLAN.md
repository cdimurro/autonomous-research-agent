# Phase 10K: Graph-Native Retrieval Promotion — Plan

**Branch:** `breakthrough-engine-phase10k-graph-native-rollout`
**Date:** 2026-03-14
**Base:** `breakthrough-engine-phase10g-retrieval-ab` @ `7e17264`

## Objective

Safe production promotion of graph-native retrieval, validated by a 6-run
burn-in (3 eval + 3 prod), with rollback readiness.

## Current State

| Item | Value |
|------|-------|
| Production branch | `breakthrough-engine-phase10g-retrieval-ab` |
| Rollout branch | `breakthrough-engine-phase10k-graph-native-rollout` |
| Base commit | `7e17264` (Phase 10J) |
| Champion policy | `evidence_diversity_v1` |
| Embedding | qwen3-embedding:4b (Regime 2) |
| Generation | qwen3.5:9b-q4_K_M |
| Prior retrieval default | ExistingFindingsSource + Semantic Scholar |
| Promoted retrieval | HybridKGEvidenceSource (graph-native) |
| Prior production baseline | `phase9e_promoted_production_regime2` (0.9126, 83.3%) |
| Phase 10J A/B result | +0.0104 score, +6.7 unique sources, all checks PASS |
| Tests | 1171 passing |

## Promotion Change

Single change in `campaign_manager.py:_run_ladder_with_retries()`:
- Construct `HybridKGEvidenceSource(trusted_source, kg_source, min_kg_items=2, max_per_paper=3)`
- Set `evidence_source_override=graph_native_source` in LadderConfig
- Set `enable_graph_context=True` in LadderConfig

This makes ALL daily profiles (evaluation + production) use graph-native retrieval.

## Rollback Path

To revert: remove the `evidence_source_override` and `enable_graph_context` lines
from the LadderConfig construction, and remove the HybridKGEvidenceSource construction
block. Or simply check out the prior branch.

## Deliverables

| ID | Deliverable | Status |
|----|-------------|--------|
| A | Safe rollout branch setup | PENDING |
| B | Retrieval promotion execution | PENDING |
| C | Production/evaluation burn-in (3+3) | PENDING |
| D | Review label collection | PENDING |
| E | Burn-in comparison summary | PENDING |
| F | New production baseline freeze | PENDING |
| G | Rollback/reversion validation | PENDING |
| H | Final adoption decision | PENDING |
| I | Testing | PENDING |
| J | Artifact packaging | PENDING |
| K | Branch/commit strategy | PENDING |
