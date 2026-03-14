# Phase 10J: KG Corpus Diversification, Source-Aware Hybrid Retrieval, Promotion-Unblocking A/B

**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Date:** 2026-03-14

## Objective

Remove the final blocker preventing graph-native retrieval promotion:
evidence-pool concentration where all evidence packs contain items from
a single paper (arxiv:2402.11234).

## Root Cause (Discovered in Phase 10J Audit)

Three interacting issues combine to produce unique_sources=1.0:

### Issue 1: evidence_refs bypass (PRIMARY)

The candidate generator sets `evidence_refs` on all candidates, pointing to
specific evidence item IDs. In `_run_evidence_gate()`:

```python
if c.evidence_refs:
    items = [e for e in evidence if e.id in c.evidence_refs]
```

This **completely skips** `rank_evidence()` and `select_diverse_top_k()`.
For graph-conditioned candidates, ALL refs point to items from arxiv:2402.11234
because the graph context is derived from that paper's KG content.

### Issue 2: KG items excluded from hybrid pool

HybridKGEvidenceSource combines trusted + KG items, sorts by relevance, and
trims to `limit`. KG items (calibrated to ~0.75-0.88) lose to trusted findings
(0.81-0.93). Result: `kg_items=0` in every pool.

### Issue 3: Pool diversity exists but is never used

The evidence pool actually has 15 unique source_ids from 20 items (5 per-domain
gather × 2 domains + KG items). But because evidence_refs bypasses ranking,
this diversity is never reached.

## Fixes

### Fix A: Diversity-aware evidence_refs handling

In `_run_evidence_gate()`, after matching evidence_refs, check source diversity
of matched items. If unique sources < k, fall through to rank_evidence +
select_diverse_top_k.

### Fix B: Source-aware hybrid pool construction

In HybridKGEvidenceSource, guarantee a minimum number of KG items in the
combined pool by reserving slots, rather than letting them compete purely
on relevance score.

### Fix C: KG corpus breadth check

Verify the existing KG corpus (390 papers, 1894 entities, 1273 relations)
is sufficient. If not, expand by ingesting additional papers.

## Constraints

- Do not merge to main
- Do not switch live production retrieval
- Policy: evidence_diversity_v1 (fixed)
- Embedding: qwen3-embedding:4b (fixed)
- Generation: qwen3.5:9b-q4_K_M (fixed)
- All tests offline-safe
- One-publication-per-run invariant preserved

## Deliverables

| ID | Deliverable | Status |
|----|-------------|--------|
| A | Corpus concentration audit | COMPLETE |
| B | KG corpus breadth verification | PENDING |
| C | Source-aware hybrid pool construction | PENDING |
| D | Diversity-aware evidence_refs handling | PENDING |
| E | Hybrid selection diagnostics | PENDING |
| F | Comparability re-check | PENDING |
| G | Confirmatory A/B (7+7) | PENDING |
| H | Review label collection | PENDING |
| I | Final comparison summary | PENDING |
| J | Switch decision | PENDING |
| K | Rollback readiness | PENDING |
| L | Testing | PENDING |
| M | Artifact packaging | PENDING |
