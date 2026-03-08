# Phase 5 Plan: Cross-Domain Synthesis

## Status: In Progress

## Objective

Add cross-domain synthesis capability to the Breakthrough Engine. Generate hybrid hypotheses that intentionally bridge two domains (e.g., clean-energy + materials), with proper evidence assembly, fit scoring, novelty evaluation, and operator visibility.

## Starting Point

| Item | Value |
|------|-------|
| Base tag | `breakthrough-engine-phase4d-validated` (063ebb4) |
| Branch | main |
| Tests | 325 passed, 0 failed |
| Schema | v005 |
| Generation model | qwen3.5:9b-q4_K_M (Ollama) |
| Embedding model | nomic-embed-text (Ollama, 768d) |
| Embedding threshold | 0.88 (unchanged) |
| Domains | clean-energy (10 sub-domains), materials (10 sub-domains) |
| Phase 4D block rate | 0% (both domains) |

## Implementation Order

### Priority 1: Cross-Domain Pairing + Synthesis Generation
- `breakthrough_engine/synthesis.py` — SynthesisContext, DomainPairPolicy, SynthesisEngine
- Extend `candidate_generator.py` — synthesis-aware prompting
- Config: `config/domain_fit/cross_domain.yaml` updates, cross-domain sub-domains

### Priority 2: Evidence Packs + Fit Scoring
- Extend evidence assembly for dual-domain evidence with role tagging
- Add `SynthesisFitEvaluator` to score cross-domain quality
- Penalize shallow mashups

### Priority 3: Hybrid Run Policies + Novelty
- Extend novelty to handle cross-domain prior art diagnostics
- Add `cross_domain_pair` run policy to scheduler/orchestrator
- Research program configs for synthesis runs

### Priority 4: Operator Visibility + Validation
- Synthesis metadata in draft/review views
- Live validation with real Ollama runs
- Bounded stress-check script

### Priority 5: Tests + Docs
- Comprehensive test coverage for all new components
- Final documentation and status report

## Constraints

1. Do not redesign the architecture
2. Do not weaken novelty thresholds
3. Extend (not replace) single-domain workflows
4. All tests offline-safe
5. One-publication-per-run invariant preserved
6. Safe run modes and operator approval preserved
7. Synthesis decisions explainable and auditable

## Schema Changes

v006: Add synthesis-specific tables
- `bt_synthesis_context` — per-run synthesis pairing/bridge metadata
- `bt_synthesis_fit` — per-candidate synthesis quality scores

## New Files

| File | Purpose |
|------|---------|
| `breakthrough_engine/synthesis.py` | SynthesisEngine, SynthesisContext, pairing policies |
| `tests/test_breakthrough/test_phase5.py` | Phase 5 tests |
| `scripts/stress_check.py` | Bounded stress-check script |
| `config/research_programs/cross_domain_shadow.yaml` | Cross-domain shadow program |
| `config/research_programs/cross_domain_review.yaml` | Cross-domain review program |

## Modified Files

| File | Change |
|------|--------|
| `breakthrough_engine/db.py` | v006 migration |
| `breakthrough_engine/orchestrator.py` | Synthesis context wiring, cross-domain evidence |
| `breakthrough_engine/candidate_generator.py` | Synthesis-aware prompt addendum |
| `breakthrough_engine/diversity.py` | Cross-domain sub-domain support |
| `breakthrough_engine/novelty.py` | Cross-domain novelty diagnostics |
| `breakthrough_engine/scoring.py` | Synthesis fit bonus |
| `breakthrough_engine/review.py` | Synthesis metadata in drafts |
