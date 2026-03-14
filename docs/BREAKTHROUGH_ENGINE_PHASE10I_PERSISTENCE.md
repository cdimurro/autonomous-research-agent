# Phase 10I: Evidence Item Persistence Repair

**Date:** 2026-03-14

## Problem

Phase 10H found that only 1/7 evidence packs per run had stored items in
`bt_evidence_items` (244/1589 packs across the experiment had stored items).
This made diversity measurements unreliable — only the last pack's items
were visible, not all candidates' evidence.

## Root Cause

In `orchestrator.py:_run_evidence_gate()`:

1. Evidence is gathered **once per run** (20 items from the evidence source)
2. ALL candidates in the run share the **same `EvidenceItem` objects**
3. Each candidate's `EvidencePack` references items with the **same IDs**
4. `save_evidence_pack()` in `db.py` uses `INSERT OR REPLACE INTO bt_evidence_items`
5. When pack 2 saves item A (same ID), it **overwrites** pack 1's row for item A
6. Result: only the **last pack saved** retains its items in the database

### Example

```
Run: 7 candidates, evidence pool has 20 items, top-2 selected for each pack

Pack 1 saves: item_abc → pack_1, item_def → pack_1   ✓
Pack 2 saves: item_abc → pack_2, item_def → pack_2   overwrites pack_1's items
Pack 3 saves: item_abc → pack_3, item_def → pack_3   overwrites pack_2's items
...
Pack 7 saves: item_abc → pack_7, item_def → pack_7   only this one survives
```

After all saves: bt_evidence_items has 2 rows, both pointing to pack_7.
Packs 1-6 have 0 items in the DB despite having been saved correctly at their time.

## Fix

Create fresh `EvidenceItem` copies with new IDs for each pack:

```python
pack_items = [
    EvidenceItem(
        id=new_id(),  # Fresh ID for this pack
        source_type=item.source_type,
        source_id=item.source_id,  # Preserved for diversity counting
        title=item.title,
        quote=item.quote,
        citation=item.citation,
        relevance_score=item.relevance_score,
    )
    for item in items
]
pack = EvidencePack(
    candidate_id=c.id,
    items=pack_items,
    source_diversity_count=len(set(i.source_id for i in pack_items)),
)
```

Key properties:
- Each pack's items have **unique IDs** → no INSERT OR REPLACE collisions
- Content fields (`source_id`, `title`, `quote`, etc.) are preserved exactly
- `source_diversity_count` computed from pack-specific items

## Expected Impact

| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| Packs with stored items | ~1/7 per run | 7/7 per run |
| Evidence items per run | 2 | 14 (7 × 2) |
| Persistence rate | ~14% | ~100% |
| Diversity measurement | Unreliable | Trustworthy |

## Verification

- `test_pack_items_get_unique_ids`: Confirms pack item IDs are disjoint across packs
- `test_pack_preserves_content`: Confirms content fields are preserved in copies
- A/B script now tracks `packs_with_items`, `total_packs`, `persistence_rate`
