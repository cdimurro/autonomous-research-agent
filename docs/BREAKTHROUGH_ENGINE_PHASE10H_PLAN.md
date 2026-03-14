# Phase 10H: Diversity Metric Hardening, Graph Caching, and Extended Limited Retrieval A/B

**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Date:** 2026-03-13

## Objective

Fix the diversity measurement blind spot from Phase 10G, reduce graph-native overhead
via caching, run a larger A/B (7+7), and produce a final promotion decision.

## Context

Phase 10G's only failed threshold was `diversity_ge_current`. Root cause: KG segments
from the same paper shared paper-level `source_id`, collapsing diversity to 1. This is
a measurement artifact, not a real regression.

## Deliverables

| Deliverable | Description | Status |
|-------------|-------------|--------|
| A | Diversity metric hardening — segment-level source_ids | COMPLETE |
| B | Graph caching in orchestrator | COMPLETE |
| C | Comparability lock re-check | COMPLETE |
| D | Extended limited retrieval A/B (7+7) | COMPLETE |
| E | Review label collection | COMPLETE (28 labels) |
| F | Final comparison summary | COMPLETE |
| G | Final switch decision | COMPLETE (`continue_limited_ab`) |
| H | Rollback readiness | COMPLETE |
| I | Testing | COMPLETE (1142 passing) |
| J | Artifact packaging | COMPLETE |
| K | Commit | PENDING |

## Key Changes

### A: Diversity Metric Fix (`kg_retrieval.py`)

```python
# Before (paper-level — caused diversity collapse)
source_id=seg.get("source_id", seg.get("paper_id", "")),

# After (segment-level — fair diversity measurement)
seg_id = seg.get("id", seg.get("paper_id", ""))
source_id=f"kg_seg:{seg_id}",
```

### B: Graph Caching (`orchestrator.py`)

Module-level `_graph_cache` class variable keyed by `(domain, entity_count, relation_count)`.
Caches: canonical_map, stats, graph, reasoning paths. Only topic subgraph (evidence-dependent)
rebuilt per run. Added `_invalidate_graph_cache()` classmethod and timing diagnostics.

## Constraints

- Do NOT merge to main
- Do NOT switch production retrieval default
- Policy fixed to evidence_diversity_v1
- Embedding fixed to qwen3-embedding:4b (Regime 2)
- Generation fixed to qwen3.5:9b-q4_K_M
