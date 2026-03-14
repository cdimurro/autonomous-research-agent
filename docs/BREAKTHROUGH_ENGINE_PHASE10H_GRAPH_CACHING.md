# Phase 10H: Graph Caching

**Date:** 2026-03-13

## Motivation

Graph context construction in `_build_graph_context()` is expensive:
1. `ConceptCanonicalizer` — entity deduplication
2. Graph structure building — adjacency from relations
3. `CanonicalMultiHopReasoner` — BFS path finding (most expensive)
4. `SubgraphBuilder` — topic-dependent subgraph extraction

Steps 1-3 are deterministic on stable KG data and can be cached across runs
within a daily cycle. Only step 4 (topic subgraph) depends on per-run evidence.

## Implementation

Module-level class variable `_graph_cache` on `BreakthroughOrchestrator`:

```python
_graph_cache: dict = {}  # class-level cache

@classmethod
def _invalidate_graph_cache(cls):
    cls._graph_cache.clear()
```

Cache key: `(domain, entity_count, relation_count)` — invalidates automatically
when KG data changes (new entities or relations added).

Cached values:
- `canonical_map` — entity name → canonical form
- `stats` — entity/relation counts
- `graph` — adjacency structure
- `paths` — reasoning paths from BFS

Per-run: only `SubgraphBuilder.build()` runs fresh (needs evidence topics).

## Timing Diagnostics

Added to graph context log line:
```
cache=HIT/MISS graph_ms=X subgraph_ms=Y
```

Expected: ~95% cache hit rate within a daily campaign cycle. First run pays
full cost; subsequent runs skip canonicalization, graph building, and path finding.

## Cache Invalidation

- Automatic: cache key includes entity/relation counts, so new KG data misses
- Manual: `BreakthroughOrchestrator._invalidate_graph_cache()`
- Process boundary: cache is in-process only, cleared on restart
