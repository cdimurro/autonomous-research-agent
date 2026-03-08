# Breakthrough Engine - Phase 4B Plan

## Status: Complete

## Scope

Phase 4B: Retrieval Quality + Novelty Enhancement

Building on Phase 4A's operational baseline (12 shadow runs, 3 review runs, 176 tests), Phase 4B strengthens trust and discrimination in the pipeline.

## Priorities

| Priority | Deliverable | Status |
|----------|-------------|--------|
| 0 | Preflight cleanup (doc drift, model strategy, trust gaps) | Done |
| 1 | Evidence linking, domain-fit enforcement, retrieval ranking | Done |
| 2 | Embedding-based novelty engine with persistence | Done |
| 3 | Novelty/publication calibration and diagnostics | Done |
| 4 | Minimal operator review visibility improvements | Done |
| 5 | Tests, docs, final status report | Done |

## Evidence-Based Rationale

From Phase 4A observations:
1. **evidence_refs fallback to first 2 items** — LLM output rarely produces valid evidence reference numbers, so evidence linking defaulted to the first 2 items. Fixed with ranked evidence matching.
2. **100% publication gate pass rate** — All 33 checked candidates passed publication gate. Added diagnostic explanations and additional warning signals.
3. **All-pass novelty** — Diverse LLM outputs never triggered lexical novelty gates. Added embedding-based semantic similarity layer.
4. **Domain mismatch in demo mode** — Candidates sometimes don't fit the research program domain. Added domain-fit gate with keyword-based scoring.

## Constraints

1. No architecture redesign
2. No live Omniverse execution
3. No full dashboard (minimal review UI only)
4. All tests offline-safe (no network, no Ollama)
5. Preserve one-publication-per-run invariant
6. Keep novelty decisions explainable
7. Only tighten thresholds where justified by Phase 4A evidence
