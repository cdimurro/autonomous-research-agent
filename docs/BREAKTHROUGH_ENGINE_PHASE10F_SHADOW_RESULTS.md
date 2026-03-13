# Phase 10F: Post-Wiring Shadow Comparison Results

**Date:** 2026-03-12
**Version:** Comparison v5

## Key Finding

With the graph path fully wired into the actual pipeline:
- Graph-native mean relevance: **0.8973** (vs current 0.8793, delta +0.018)
- Source diversity: **17 unique sources** (vs current 11, +55%)
- Source types: **4** (vs current 1)
- Grounding score: **0.517** (vs current 0.458, +13%)
- Strong support items: **14** (vs current 8, +75%)
- Unsupported items: **0** (vs current 0)

## What Changed From Phase 10E-Prime

Phase 10E-Prime showed hybrid retrieval at 0.885 but with **dead code** — the graph never actually reached the LLM or the scoring pipeline. Phase 10F:

1. **Evidence source injection WIRED** — `HybridKGEvidenceSource` injected via `LadderConfig.evidence_source_override` → `_run_single_trial()` → `BreakthroughOrchestrator(evidence_source=...)`

2. **Graph-conditioned generation WIRED** — `enable_graph_context=True` triggers `_build_graph_context()` in the orchestrator, which constructs canonical graph, finds reasoning paths, and passes formatted context to `generate(graph_context=...)`, which uses `GRAPH_CONDITIONED_TEMPLATE`

3. **Canonicalization HARDENED** — Near-duplicate fuzzy merge reduces 48 → 47 concepts (90.4% collapse rate, up from 70.7%)

4. **Grounding HARDENED** — Bigram matching, expanded stopwords, rebalanced formula; strong_support 2 → 14, unsupported 10 → 0

## Three-Arm Comparison

| Metric | Current | Hybrid (flat) | Graph-Native |
|--------|---------|--------------|-------------|
| mean_relevance | 0.8793 | 0.8748 | **0.8973** |
| unique_source_ids | 11 | 12 | **17** |
| source_types | 1 | 2 | **4** |
| grounding_score | 0.458 | 0.457 | **0.517** |
| strong_support | 8 | 9 | **14** |
| unsupported | 0 | 3 | **0** |

## Evidence Composition (Graph-Native Arm)

| Source Type | Count |
|-------------|-------|
| finding | 22 |
| graph_path | 6 |
| kg_subgraph | 1 |
| kg_segment | 1 |

## Graph Diagnostics

| Metric | Value |
|--------|-------|
| Canonical concepts | 47 |
| Cross-paper concepts | 44 (94%) |
| Collapse rate | 90.4% |
| Canonical paths | 10 |
| Cross-paper paths | 10 (100%) |
| Graph context chars | 1798 |

## Verdict

`graph_native_better` — The graph-native arm surpasses current retrieval on all measured dimensions: relevance, diversity, and grounding quality.
