# Phase 10J: Corpus Concentration Audit

**Date:** 2026-03-14

## KG Corpus Statistics

| Metric | Count |
|--------|-------|
| Papers (bootstrap) | 24 |
| Accepted findings | 53 |
| KG paper segments | 396 (from 390 unique paper_ids) |
| KG entities | 1,894 (193 canonical) |
| KG relations | 1,273 |
| Papers with segments | 390 |
| Papers with findings | 24 |
| Overlap (segments ∩ findings) | 12 |

## Concentration Analysis

### At the Findings Layer

Findings matching "clean-energy" domain filter: 36 from 12 unique papers.

Top papers by finding count:
- arxiv:2402.11234: 2 findings (conf 0.93)
- arxiv:2312.09215: 4 findings (conf 0.88-0.92)
- doi:10.1126/science.adf6211: 4 findings (conf 0.89-0.90)
- doi:10.1038/s41586-024-07892-1: 2 findings (conf 0.84-0.91)

**Assessment:** Findings are reasonably diverse across 12+ papers.

### At the KG Segment Layer

396 segments from 390 unique papers. Top paper has only 2 segments.

**Assessment:** KG segments are NOT concentrated. Broad coverage.

### At the HybridKGEvidenceSource Pool Layer (Pre-Fix)

For domain="clean-energy" with limit=10:
- Total items: 10
- Trusted items: 10
- **KG items: 0** (all excluded by relevance sort)
- Unique source_ids: 5
- Top-1 concentration: 20%

**Assessment:** Pool is diverse at the paper level, but KG items are completely
excluded because their calibrated relevance scores (0.75-0.88) lose to trusted
findings (0.81-0.93) in the pure relevance sort.

### At the Evidence Pack Layer (Critical Finding)

Phase 10I result: ALL evidence packs in graph-native arm contain items ONLY
from arxiv:2402.11234 (source_type=finding).

**Root cause:** The candidate generator sets `evidence_refs` on ALL candidates,
pointing to 2 specific items from the evidence pool. For graph-conditioned
candidates, both refs point to items from arxiv:2402.11234 because the graph
context is derived from that paper. In `_run_evidence_gate()`:

```python
if c.evidence_refs:
    items = [e for e in evidence if e.id in c.evidence_refs]
```

This completely bypasses `rank_evidence()` and `select_diverse_top_k()`.

## Fix Summary

1. **evidence_refs diversity check** (orchestrator.py): When matched items have
   fewer unique sources than top_k, clear items and fall through to ranking.

2. **Source-aware hybrid pool** (hybrid_retrieval.py): Reserve `min_kg_items=2`
   slots in the combined pool for KG items. Apply `max_per_paper=3` cap to
   prevent any single paper from dominating. Select diverse KG items preferring
   distinct sources.

## Post-Fix Pool Analysis

For domain="clean-energy" with limit=10 after fixes:
- Total items: 10
- Trusted items: 8
- **KG items: 2** (now guaranteed via slot reservation)
- Unique source_ids: 7
- Top-1 concentration: 20%
