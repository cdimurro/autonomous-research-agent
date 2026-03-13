# Phase 10E: KG Switch-Readiness Decision

**Date:** 2026-03-12
**Recommendation:** `keep_shadow_only`

## Decision

The upgraded hybrid retrieval system (with multi-hop reasoning and cross-paper synthesis) is **NOT ready** for production A/B trial.

**Primary failure:** Score preservation check failed. Hybrid mean relevance (0.8155) is 0.064 points below current production (0.8793), exceeding the -0.01 tolerance threshold.

## Threshold Checks

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| score_preservation | >= 0.8693 | 0.8155 | **FAIL** |
| diversity_improvement | >= 11 unique sources | 12 | PASS |
| source_type_diversity | > 1 source type | 3 | PASS |

## What Improved vs Phase 10D

| Metric | Phase 10D Hybrid | Phase 10E Hybrid | Change |
|--------|-----------------|-----------------|--------|
| Source types | 2 | 3 | +1 (graph_path) |
| Unique sources | 11 | 12 | +1 |
| Reasoning paths | N/A | 50 | New capability |
| Synthesis links | N/A | 20 | New capability |
| Evidence grounding | N/A | Available | New capability |

## What Degraded

| Metric | Phase 10D Hybrid | Phase 10E Hybrid | Change |
|--------|-----------------|-----------------|--------|
| mean_relevance | 0.8725 | 0.8155 | -0.057 |

The score degradation is caused by adding graph_path evidence items (10 items) and kg_segment items (12 items) that dilute the high-scoring findings (13 items).

## Bottleneck Analysis

### Critical: Extraction Coverage (6.8%)
Only 27 of 396 segments have been processed through KG extraction. This means:
- The graph has only 168 nodes from a small fraction of the corpus
- Cross-paper paths cannot form because most papers have zero entities
- Synthesis bridges are limited to the few extracted segments

### High: Entity Canonicalization
0 cross-paper paths were found despite 50 total paths. Entity names like "Perovskite Solar Cell" from one paper don't match "perovskite photovoltaic" from another. Canonical name normalization is needed.

### Medium: Calibration Profile Stale
The calibration profiles (from Phase 10D) were fitted to the original score distributions. With restored embedding scores, the profiles may need recomputation.

### Low: Hybrid Quota Balance
Current settings (13 findings + 12 KG + 5 graph_path = 30 items) over-weight KG evidence relative to its quality. Reducing `kg_diversification_quota` would improve score preservation.

## Path to Production Readiness

1. **Run full extraction** — Process all 396 segments through `EntityRelationExtractor` (requires Ollama qwen3.5:9b-q4_K_M, estimated 2-3 hours)
2. **Implement entity canonicalization** — Lowercase + stemming + synonym mapping for cross-paper entity matching
3. **Re-run pipeline** — With full extraction, expect significantly more cross-paper paths and synthesis links
4. **Refit calibration** — Compute new calibration profiles from the full-extraction score distributions
5. **Tune hybrid quotas** — Target hybrid mean_relevance >= 0.8693 (current - 0.01)
6. **Re-evaluate** — If score preservation passes, proceed to bounded production A/B trial

## Comparison to Phase 10D Decision

Phase 10D recommended `ready_for_limited_production_retrieval_ab` with hybrid score 0.8725 (delta -0.0068). Phase 10E's lower hybrid score (0.8155) is because:
1. More KG items are included (graph_path evidence adds 5 items)
2. Graph path items have lower relevance scores than calibrated segments
3. The upgraded hybrid is more aggressive about adding novel evidence types

The Phase 10D hybrid configuration remains the better candidate for an initial production A/B trial.
