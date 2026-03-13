# Phase 10E: KG Reasoning Upgrade — Status

**Branch:** `breakthrough-engine-phase10a-kg-shadow`
**Base commit:** Phase 10D (on same branch)
**Date:** 2026-03-12
**Tests:** 1078 passing, 0 failures
**Schema version:** 12 (unchanged)

## Summary

Phase 10E implemented deep KG quality upgrades targeting 8 identified bottlenecks: multi-signal segment scoring, extraction confidence, multi-hop graph reasoning, cross-paper synthesis, source-aware generation, evidence grounding validation, and source-type-aware evidence strength scoring.

**Result:** Upgraded hybrid retrieval adds source-type diversity (3 types vs 1: finding + kg_segment + graph_path) and source ID diversity (12 vs 11), but score preservation fails (0.8155 vs 0.8793 current, delta -0.064).

**Recommendation:** `keep_shadow_only` — score quality gap too large for production A/B trial.

## What Was Built

| Module | Purpose |
|--------|---------|
| `kg_segment_scorer.py` | Multi-signal scoring: 5 weighted signals (embedding, keyword, quantitative, citation, mechanism) |
| `kg_reasoning.py` | Multi-hop BFS path finding (2-3 hops), cross-paper synthesis via shared-concept bridges |
| `kg_grounding.py` | Evidence grounding validation: keyword overlap + trust priors + contradiction detection |
| `kg_extractor.py` (modified) | LLM-derived confidence scores with rule-based fallback |
| `candidate_generator.py` (modified) | Source-type labels in generation prompts, EVIDENCE TYPE KEY |
| `scoring.py` (modified) | Source-type-aware trust weighting in evidence_strength_score |
| `scripts/phase10e_kg_reasoning.py` | Pipeline: non-destructive multi-signal analysis, comparison v3, switch-readiness |
| `tests/test_phase10e.py` | 37 offline-safe tests for all new modules |

## Pipeline Results (Retrieval Comparison V3)

| Metric | Current (Findings) | KG (Shadow) | Upgraded Hybrid |
|--------|-------------------|-------------|-----------------|
| **mean_relevance** | 0.8793 | 0.4888 | 0.8155 |
| **unique_source_ids** | 11 | 8 | 12 |
| **source_types** | 1 (finding) | 1 (kg_segment) | 3 (finding, kg_segment, graph_path) |
| **verdict** | — | current_better | shadow_better (vs KG-only) |

## Switch-Readiness Checks

| Check | Required | Actual | Result |
|-------|----------|--------|--------|
| score_preservation | >= 0.8693 | 0.8155 | **FAIL** |
| diversity_improvement | >= 11 | 12 | PASS |
| source_type_diversity | > 1 | 3 | PASS |

## Multi-Signal Segment Analysis

Non-destructive analysis (DB scores preserved):
- **Embedding mean:** 0.5835 (original qwen3-embedding:4b cosine similarity)
- **Composite mean:** 0.4398 (5-signal weighted: embedding 30%, keyword 20%, quantitative 20%, citation 10%, mechanism 20%)
- 6/396 segments would improve, 389 would degrade
- Most segments lack quantitative results, citations, and mechanistic language — the text-quality signals are correctly penalizing low-information segments

## Graph Reasoning Stats

| Metric | Value |
|--------|-------|
| Graph nodes | 168 |
| Graph edges | 94 |
| Multi-hop paths (2-hop) | 50 |
| Cross-paper paths | 0 |
| Path confidence mean | 0.5578 |
| Synthesis links | 20 |
| Synthesis confidence mean | 0.6000 |

## Extraction Coverage

| Metric | Value |
|--------|-------|
| Total segments | 396 |
| Extracted | 27 (6.8%) |
| Entities | 168 |
| Relations | 94 |
| Entity confidence mean | 0.600 |
| Relation confidence mean | 0.500 |

## Root Causes of Score Gap

1. **Low extraction coverage (6.8%)** — Only 27/396 segments have KG entities/relations. Graph reasoning and synthesis operate on this thin slice, limiting cross-paper discovery.
2. **No cross-paper paths** — All 50 multi-hop paths are within-paper because extracted segments likely share papers, and entity names don't match across papers without canonicalization.
3. **KG raw score gap** — KG segments score 0.4888 mean vs 0.8793 for curated findings. Calibration narrows this but can't fully close a 0.39-point gap.
4. **Hybrid dilution** — Adding 17 KG items (kg_segment + graph_path) to 13 findings dilutes the average even after calibration.

## Fixes Needed for Production Readiness

1. **Increase extraction coverage** — Run extraction on all 396 segments (currently only 27)
2. **Entity canonicalization** — Normalize entity names for cross-paper matching (e.g., "Perovskite Solar Cell" vs "perovskite solar cells")
3. **Calibration tuning** — Tighten calibration profiles using actual score distributions after full extraction
4. **Hybrid quota tuning** — Reduce `kg_diversification_quota` to limit quality dilution until KG scores improve
5. **Embedding-integrated multi-signal scoring** — Run with actual embedding provider to get real composite improvements

## Artifacts

All outputs in `runtime/phase10e/`:
- `segment_rescoring.json` — Multi-signal analysis diagnostics
- `extraction_stats.json` — Coverage and confidence stats
- `reasoning_stats.json` — Graph and synthesis stats
- `retrieval_comparison/` — V3 comparison (JSON, MD, CSV, evidence item CSVs)
- `switch_readiness.json` — Decision with threshold checks
- `switch_readiness.md` — Human-readable decision
- `manifest.json` — Deliverable index
