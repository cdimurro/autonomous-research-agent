# Phase 10B Plan: KG Population, Shadow Comparison, Switch-Readiness

## Objective

Determine whether KG-aware shadow retrieval actually beats the current retrieval path on real clean-energy data, without switching production.

## Approach

1. Populate KG staging tables with real clean-energy data from findings and evidence items
2. Run entity/relation extraction via Ollama (qwen3.5:9b-q4_K_M)
3. Compare evidence quality: current production retrieval vs KG shadow retrieval
4. Quantify diversity improvements at retrieval and campaign levels
5. Produce a hard go/no-go recommendation for a future retrieval A/B trial

## Constraints

- No production retrieval switch
- Shadow-only KG work
- Embedding regime fixed to Regime 2 (qwen3-embedding:4b, 2560d)
- All tests offline-safe
- One-publication-per-run invariant preserved

## Implementation

- `scripts/phase10b_kg_population.py` — orchestrates all deliverables
- Fix: `kg_extractor.py` brace escaping bug in extraction prompt

## Status

**COMPLETE** — see `docs/BREAKTHROUGH_ENGINE_PHASE10B_STATUS.md`
