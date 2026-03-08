# Embedding Monitoring & Drift Analysis

## Overview
Phase 4C adds per-run embedding novelty tracking and cross-run drift detection.

## Per-Run Metrics (bt_embedding_monitor)

Each run records:
- **embedding_model**: Model used (e.g., `nomic-embed-text` or `mock`)
- **embedding_dim**: Embedding dimension (768 for nomic, 64 for mock)
- **similarity_threshold / warn_threshold**: Active thresholds
- **candidates_evaluated**: Number of candidates processed
- **blocked_count**: Candidates blocked by embedding similarity
- **warned_count**: Candidates warned but not blocked
- **max_similarity**: Highest cosine similarity observed
- **mean_similarity**: Average similarity across top-k
- **top_k_similarities**: Top 10 similarity scores
- **nearest_neighbor_summary**: Most similar prior items

## Drift Report

The `EmbeddingMonitor.get_drift_report()` method analyzes recent runs:

1. **Trend data**: Per-run max/mean similarity, block/warn rates
2. **Summary stats**: Averages across runs
3. **Saturation warning**: Alerts if recent similarity scores trend higher (novelty space may be shrinking)
4. **Repeated neighbors**: Items appearing as nearest neighbors in 2+ runs (cluster detection)

## API Endpoints

- `GET /api/breakthrough/view/embedding-drift` — JSON drift report
- `GET /api/breakthrough/view/thresholds` — Current active thresholds
- `GET /api/breakthrough/view/calibration/<run_id>` — Per-run calibration diagnostics

## Schema (v004)

```sql
bt_embedding_monitor: run metrics for embedding novelty
bt_calibration_diagnostics: per-run gate pass/fail statistics
```
