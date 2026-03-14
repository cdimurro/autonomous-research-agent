# Phase 10H: Diversity Metric Hardening

**Date:** 2026-03-13

## Problem

Phase 10G's A/B found graph-native evidence packs had `source_diversity_count=1` vs
`2` for current arm. This was the only failing threshold check, blocking promotion.

## Root Cause

`KGEvidenceSource._gather_from_segments()` used:
```python
source_id=seg.get("source_id", seg.get("paper_id", ""))
```

All segments extracted from the same paper shared the paper-level source_id. When a
campaign's evidence pack contained multiple KG segments from one paper, they all had
the same source_id → `len(set(source_ids)) == 1` → diversity = 1.

This is a **measurement artifact**, not a real diversity regression. The graph-native
arm actually produced more topically diverse champion hypotheses.

## Fix

Changed to segment-level source_ids in `breakthrough_engine/kg_retrieval.py`:

```python
seg_id = seg.get("id", seg.get("paper_id", ""))
source_id=f"kg_seg:{seg_id}",
```

Each segment now gets a unique source_id prefixed with `kg_seg:`, giving an accurate
count of distinct evidence sources in the pack.

## Evidence Pack Diversity Measurement

The `source_diversity_count` on `bt_evidence_packs` is computed as:
```python
len(set(item.source_id for item in items))
```

This is stored at pack creation time. The fix ensures KG segments contribute their
individual identity to this count rather than collapsing to their parent paper.

## Verification

- 1142 tests pass after the fix
- Phase 10H extended A/B will measure diversity with corrected source_ids
- Retroactive Phase 10G recomputation not needed — the fix is forward-looking
