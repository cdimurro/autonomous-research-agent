# Phase 10J: Source-Aware Hybrid Evidence-Pool Construction

**Date:** 2026-03-14

## Problem

HybridKGEvidenceSource combined trusted + KG items, sorted by relevance, and
trimmed to `limit`. KG items (calibrated to 0.75-0.88) lost to trusted findings
(0.81-0.93) in every case, resulting in `kg_items=0` in every pool.

Additionally, the orchestrator's `evidence_refs` path directly matched
items referenced by the generator, completely bypassing `rank_evidence()`
and `select_diverse_top_k()`. For graph-conditioned candidates, ALL refs
pointed to items from arxiv:2402.11234.

## Fix 1: evidence_refs Diversity Check (orchestrator.py)

After matching evidence_refs, check source diversity of matched items.
If unique sources < top_k, clear items and fall through to ranked matching.

```python
# Phase 10J: Check diversity of evidence_refs matches
if items:
    ref_sources = set(it.source_id for it in items)
    top_k = max(self.program.evidence_minimum, 2)
    if len(ref_sources) < min(top_k, len(items)) and evidence:
        items = []  # insufficient diversity — use ranked path
```

This ensures:
- Diverse refs are preserved (no change to existing behavior)
- Non-diverse refs fall through to rank_evidence + select_diverse_top_k
- Single refs are preserved (can't be non-diverse with 1 item)

## Fix 2: Source-Aware Pool Construction (hybrid_retrieval.py)

### New Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| min_kg_items | 2 | Minimum KG items reserved in pool |
| max_per_paper | 3 | Cap per source_id in trusted items |

### Algorithm

1. Get trusted items from production source
2. Get KG items from KG source
3. Calibrate KG scores
4. Apply per-paper cap to trusted items (`max_per_paper=3`)
5. Deduplicate KG items against trusted source_ids
6. Reserve `min_kg_items` slots for KG items in the combined pool
7. Select diverse KG items (prefer distinct sources)
8. Combine: trusted (by relevance) + reserved KG
9. Fill remaining slots from leftovers
10. Sort final pool by relevance

### Diversity Guarantee

The `_select_diverse_kg()` helper selects KG items preferring items from
distinct source_ids:

1. First pass: one item per unique source
2. Second pass: fill remaining from any source

This ensures the KG contribution to the pool is itself diverse.

## Impact

### Pre-Fix Pool (Phase 10I)
- 10 items, 5 unique sources, 0 KG items
- KG items excluded by relevance sort

### Post-Fix Pool (Phase 10J)
- 10 items, 7 unique sources, 2 KG items
- KG items guaranteed via slot reservation
- Per-paper cap prevents single-paper dominance

### Pre-Fix Evidence Packs (Phase 10I)
- unique_sources = 1.0 (graph-native arm)
- ALL items from arxiv:2402.11234
- evidence_refs bypass prevented diversity

### Post-Fix Evidence Packs (Phase 10J)
- Expected unique_sources >= 2.0
- evidence_refs diversity check forces ranked path
- select_diverse_top_k enforces per-source cap
