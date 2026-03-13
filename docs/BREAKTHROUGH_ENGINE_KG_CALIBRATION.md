# KG Evidence Calibration — Phase 10D

## Problem

KG segment relevance scores (mean 0.584, range [0.322, 0.602]) are on a fundamentally different scale than production finding confidence scores (mean 0.874, range [0.810, 0.930]). This 0.29 gap is the primary cause of KG underperformance.

## Solution: Distribution-Based Linear Rescaling

Each source type has a calibration profile that maps its observed score distribution to a target range:

| Source Type | Observed Range | Target Range | Effect |
|-------------|---------------|--------------|--------|
| kg_segment | [0.322, 0.602] | [0.75, 0.88] | Calibrated up to compete with findings |
| kg_graph | [0.30, 0.70] | [0.70, 0.85] | Calibrated up, slightly below segments |
| finding | [0.810, 0.930] | [0.810, 0.930] | Identity (already on target scale) |
| paper | [0.70, 0.95] | [0.70, 0.95] | Identity |

## Properties

- **Preserves relative ordering** within each source type
- **Explainable**: raw + calibrated scores both logged
- **Not blind inflation**: top KG items (0.88) are below top findings (0.93)
- **Configurable**: custom profiles can be injected

## Implementation

Module: `breakthrough_engine/kg_calibration.py`

```python
calibrator = EvidenceCalibrator()
result = calibrator.calibrate(evidence_items)
# result.raw_scores[item.id] = original score
# result.calibrated_scores[item.id] = calibrated score
# item.relevance_score is updated in-place
```

## Validation

Phase 10D retrieval comparison confirmed calibration works:
- Hybrid mean relevance: 0.8725 (vs current 0.8793)
- Score delta: -0.0068 (within 0.01 tolerance)
