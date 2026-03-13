# Hybrid Retrieval — Phase 10D

## Concept

Instead of replacing production retrieval with KG, combine both:
- **Trusted anchors**: Production findings (high confidence, proven quality)
- **KG diversification**: KG segments (different sources, broader coverage)

## Design

`HybridKGEvidenceSource` composes two sources with controls:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| min_trusted_quota | 10 | Minimum trusted finding items |
| max_single_source_pct | 0.50 | Cap on any single source_id's share |
| kg_diversification_quota | 10 | Maximum KG items to add |
| calibrator | EvidenceCalibrator() | Source-aware score calibration |

## Flow

1. Gather trusted items (production findings)
2. Gather KG items
3. Calibrate KG item scores
4. Cap single-source concentration in trusted items
5. Take trusted quota
6. Deduplicate KG against trusted source_ids
7. Take KG diversification quota
8. Combine, sort by relevance, trim to limit

## Diagnostics

Every `gather()` call produces `HybridMixDiagnostics`:
- trusted_items / kg_items counts
- deduplicated count
- unique_source_ids
- top1_concentration
- source_type breakdown

## Results (Phase 10D)

| Metric | Current | Hybrid |
|--------|---------|--------|
| Mean relevance | 0.8793 | 0.8725 |
| Source types | 1 | 2 |
| Top-1 concentration | — | 13.3% |
| Mix | 30 findings | 20 findings + 10 kg_segments |

## Implementation

Module: `breakthrough_engine/hybrid_retrieval.py`

```python
hybrid = HybridKGEvidenceSource(
    trusted_source=ExistingFindingsSource(db),
    kg_source=KGEvidenceSource(repo),
    min_trusted_quota=10,
    kg_diversification_quota=10,
)
items = hybrid.gather("clean-energy", limit=30)
print(hybrid.last_diagnostics.to_dict())
```
