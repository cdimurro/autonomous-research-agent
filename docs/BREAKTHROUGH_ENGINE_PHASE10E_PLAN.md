# Phase 10E: KG Reasoning Upgrade — Plan

**Branch:** `breakthrough-engine-phase10a-kg-shadow`
**Goal:** Make KG materially better, not just different.

## Deliverables

| ID | Deliverable | Status |
|----|------------|--------|
| A | Multi-signal segment scoring | DONE — `kg_segment_scorer.py` |
| B | Extraction confidence upgrade | DONE — `kg_extractor.py` modified |
| C | Extraction coverage stats | DONE — pipeline step B/C |
| D | Multi-hop graph reasoning | DONE — `kg_reasoning.py` |
| E | Cross-paper synthesis | DONE — `kg_reasoning.py` (CrossPaperSynthesizer) |
| F | Source-aware generation inputs | DONE — `candidate_generator.py` modified |
| G | Evidence grounding validation | DONE — `kg_grounding.py` |
| H | Source-type-aware evidence strength | DONE — `scoring.py` modified |
| I | Retrieval comparison v3 | DONE — `scripts/phase10e_kg_reasoning.py` |
| J | Regression tests | DONE — `tests/test_phase10e.py` (37 tests) |
| K | Switch-readiness recommendation | DONE — `keep_shadow_only` |
| L | Write-back status | DONE — 0 rows, shadow-only |
| M | Documentation | DONE — 4 doc files |

## Constraints

- Do NOT switch production retrieval
- Do NOT merge to main
- All tests offline-safe (no network calls)
- Preserve existing embedding scores in DB (non-destructive analysis)

## Key Design Decisions

1. **Non-destructive re-scoring** — Multi-signal analysis computes composite scores in memory only; DB retains original embedding-based relevance_score
2. **Geometric mean for path confidence** — Penalizes paths with any low-confidence link rather than averaging away weakness
3. **Source-type trust priors** — Curated findings get 1.0 trust, declining through KG sources to 0.70 for synthesis
4. **Enhanced diversity bonus** — Rewards both source ID and source type diversity in scoring formula
