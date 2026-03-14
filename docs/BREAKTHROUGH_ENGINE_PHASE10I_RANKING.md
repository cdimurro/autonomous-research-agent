# Phase 10I: Ranking-Layer Diversity Diagnosis & Fix

**Date:** 2026-03-14

## Diagnosis

### Problem

Graph-native retrieval produces diverse evidence (5+ unique sources from
HybridKGEvidenceSource), but `rank_evidence()` collapses this diversity by
selecting top-k items purely by composite score. When multiple KG segments
from the same paper have high mechanism_overlap, all top-k items come from
that single paper.

### Quantification (Phase 10H data)

| Metric | Current Arm | Graph-Native Arm |
|--------|------------|-----------------|
| Pre-ranking unique sources | 5+ | 5+ |
| Post-ranking unique sources | 2.0 | 1.0 |
| Top source concentration | 50% | 100% |
| Evidence pack diversity score | 1.0 | 0.5 |

### Root Cause

In `rank_evidence()`:
- Composite score = api_relevance × 0.35 + domain_overlap × 0.30 + mechanism_overlap × 0.20 + recency + baseline × 0.15
- KG segments from the same paper about the candidate's mechanism all get
  high mechanism_overlap scores (up to 1.0)
- No source diversity component in the composite score
- Naive top-k selection (`ranked[:2]`) naturally concentrates

In the orchestrator (`_run_evidence_gate`):
```python
items = [item for item, _ in ranked[:max(self.program.evidence_minimum, 2)]]
```
This takes the top-2 by score, regardless of source diversity.

## Fix: `select_diverse_top_k()`

### Algorithm

1. Iterate through ranked items in composite score order
2. Track per-source counts
3. Skip items from sources at their cap (default: 1 per source)
4. Allow bypass only when:
   - Other sources are already represented in selected set
   - The item's score exceeds the best other-source score by >= 0.15
5. If caps prevent filling k, relax and fill from remaining items

### Properties

- **Quality-preserving**: First selected item is always the highest-scored
- **Diversity-aware**: Second item comes from a different source (when available)
- **Not random**: Selection is deterministic and quality-ordered
- **Explainable**: Each item gets `diversity_penalty`, `effective_score`, and
  `source_capped` annotations in its detail dict

### Integration

In `orchestrator.py:_run_evidence_gate()`:
```python
diverse_selected = select_diverse_top_k(
    ranked, k=top_k, max_per_source=1,
)
items = [item for item, _ in diverse_selected]
```

## Verification

18 tests in `test_phase10i.py` covering:
- Basic diversity selection
- Concentration prevention (the exact bug scenario)
- Per-source cap enforcement (cap=1 and cap=2)
- Relaxation fallback
- Quality preservation
- Detail annotations
- Integration with graph-native and current retrieval scenarios
