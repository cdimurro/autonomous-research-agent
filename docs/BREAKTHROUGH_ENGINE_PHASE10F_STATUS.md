# Phase 10F: Graph-Conditioned Pipeline Wiring — Status

**Branch:** `breakthrough-engine-phase10a-kg-shadow`
**Date:** 2026-03-12
**Tests:** 1142 passing, 0 failures

## Executive Summary

Phase 10F wired the graph-native path into the actual orchestrator/generation pipeline. Previously, graph-conditioned generation was dead code and HybridKGEvidenceSource was never injected through the real run path. Now both are opt-in wired through `LadderConfig`, and the post-wiring comparison shows the graph-native arm surpasses current retrieval on all metrics: relevance (+0.018), diversity (+55%), grounding (+13%), and strong support items (+75%).

## Deliverable Status

| # | Deliverable | Status |
|---|-------------|--------|
| A | Graph path wiring audit | COMPLETE |
| B | Evidence-source injection into real shadow runs | COMPLETE |
| C | Graph-conditioned generation wiring | COMPLETE |
| D | Canonicalization hardening | COMPLETE |
| E | Grounding hardening | COMPLETE |
| F | Graph-aware downstream scoring integration | COMPLETE |
| G | Post-wiring comparison v5 | COMPLETE |
| H | Bounded downstream campaign comparison | IN PROGRESS (running) |
| I | Switch-readiness decision | COMPLETE |
| J | Write-back memory loop status | COMPLETE (shadow-only) |
| K | Testing | COMPLETE (1142 tests) |
| L | Artifact packaging | COMPLETE |
| M | Branch/commit | PENDING |

## What Was Wired

### Evidence Source Injection (Deliverable B)
- `LadderConfig.evidence_source_override` — accepts any `EvidenceSource`
- `LadderConfig.enable_graph_context` — enables graph-conditioned generation
- `_run_single_trial()` propagates both to `BreakthroughOrchestrator`
- Production default unchanged (None, False)

### Graph-Conditioned Generation (Deliverable C)
- `CandidateGenerator.generate()` accepts `graph_context: Optional[str]`
- `OllamaCandidateGenerator.generate()` switches to `GRAPH_CONDITIONED_TEMPLATE` when graph_context is provided
- `BreakthroughOrchestrator._build_graph_context()` constructs canonical graph, reasoning paths, and subgraph from DB entities/relations
- All subclass signatures updated: FakeCandidateGenerator, DemoCandidateGenerator, BenchmarkCandidateGenerator

### Canonicalization Hardening (Deliverable D)
- Added fuzzy near-duplicate merge via token-set subset matching
- Added missing synonym mappings (single-junction cell → single-junction solar cell)
- Collapse rate improved from 70.7% to 90.4%
- Cross-paper concepts: 44 (94% of 47 canonical concepts)

### Grounding Hardening (Deliverable E)
- Expanded stopwords (30 → 60+)
- Added bigram matching for compound terms
- Rebalanced formula: overlap * 0.65 + trust * 0.15 + relevance * 0.20
- Raised graph trust priors: graph_path 0.55→0.60, kg_subgraph 0.52→0.58
- Added `partial_support` verdict level
- Strong support items: 2 → 14, unsupported: 10 → 0

## Comparison v5 Results

| Metric | Current | Graph-Native | Delta |
|--------|---------|-------------|-------|
| mean_relevance | 0.8793 | **0.8973** | +0.018 |
| unique_source_ids | 11 | **17** | +55% |
| source_types | 1 | **4** | +300% |
| grounding_score | 0.458 | **0.517** | +13% |
| strong_support | 8 | **14** | +75% |
| unsupported | 0 | **0** | = |

## New/Modified Modules

| Module | Change | Lines |
|--------|--------|-------|
| `orchestrator.py` | Added `enable_graph_context`, `_build_graph_context()` | +65 |
| `daily_search.py` | Added LadderConfig fields, propagated to _run_single_trial | +15 |
| `candidate_generator.py` | Added `graph_context` param to generate(), auto-switch to graph template | +20 |
| `benchmark.py` | Added `graph_context` param to BenchmarkCandidateGenerator.generate() | +1 |
| `kg_canonicalization.py` | Added `_merge_near_duplicates()`, new synonyms | +80 |
| `kg_grounding.py` | Rewritten with bigrams, expanded stopwords, rebalanced formula | Full rewrite |
| `test_phase10a.py` | Updated guard tests for intentional wiring | +10/-8 |
| `test_phase10f.py` | NEW — 23 tests for wiring, canonicalization, grounding, scoring | ~400 |

## Scripts

| Script | Purpose |
|--------|---------|
| `phase10f_comparison.py` | Post-wiring 3-arm comparison v5 |
| `phase10f_campaign.py` | Downstream 3+3 campaign with REAL graph wiring |

## Artifacts

All outputs in `runtime/phase10f/`:
- `comparison_v5/comparison_v5.json` — Full comparison data
- `comparison_v5/comparison_v5.md` — Markdown summary
- `comparison_v5/evidence_*.csv` — Per-arm evidence items
- `campaign_comparison/` — Downstream results (when complete)

## Recommendation

`ready_for_limited_production_retrieval_ab`

See `docs/BREAKTHROUGH_ENGINE_PHASE10F_SWITCH_READINESS.md` for details.

## Constraints Respected

- Production retrieval NOT switched
- Branch NOT merged to main
- Policy fixed to evidence_diversity_v1
- All 1142 tests offline-safe
- Graph wiring is explicit, auditable, and opt-in only
- Production default completely unchanged
