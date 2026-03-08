# Phase 4D Plan: Diversity-Aware Generation

## Objective

Reduce novelty saturation without weakening thresholds. Phase 4C showed that 90% of candidates are blocked by the embedding novelty gate in clean-energy — not because thresholds are wrong, but because 120+ prior candidates create a dense semantic space.

**Key constraint: never loosen novelty thresholds. Fix saturation at generation, not at matching.**

## Root Cause

The clean-energy corpus has 120+ candidates from Phase 4A/4B/4C runs. The nomic-embed-text embedding space clusters tightly around the initial hypothesis types (perovskite solar, AEM electrolyzers, etc.). New generation hits the same semantic regions repeatedly.

## Strategy

Inject diversity context **upstream** (before the LLM generates candidates), steering toward unexplored sub-domains and away from saturated topics. This does not change the novelty gate — it changes what gets generated.

## Architecture

```
prior blocked candidates → DiversityEngine → DiversityContext
                                                    ↓
evidence + diversity addendum → OllamaCandidateGenerator → candidates
                                                    ↓
                                          NoveltyEngine (unchanged)
```

## Deliverables

### A. DiversityContext dataclass
- Per-run steering: sub_domain, excluded_topics, excluded_neighbor_titles, focus_areas
- Persisted to bt_diversity_context for analysis
- Passed to candidate generators as optional parameter

### B. Negative memory from blocked candidates
- DiversityEngine extracts topic phrases from recently-blocked candidate titles
- Injected as "AVOID THESE OVER-EXPLORED TOPICS" in prompt addendum
- Capped at 10 topics to avoid prompt bloat

### C. Sub-domain rotation
- 10 sub-domains per domain (solar, grid storage, hydrogen, wind, etc.)
- Rotates every 2 runs (SUB_DOMAIN_ROTATION_INTERVAL)
- State persisted in bt_rotation_state
- Configurable via domain_fit YAML sub_domains field

### D. Multi-domain: materials science support
- config/domain_fit/materials.yaml with 10 sub-domains
- 12 papers / 16 findings bootstrapped (seed_materials())
- DiversityEngine sub-domain rotation works for materials domain

### E. Corpus management (CorpusManager)
- Active vs archived candidate tracking
- Archival by age (default: 30 days) for non-published candidates
- Archival by cluster saturation (keep newest N, archive rest)
- bt_corpus_archive table for archived candidates
- is_archived() / archive_candidate() on Repository

### F. Domain-scoped novelty
- NoveltyEngine already scopes to domain (existing)
- CorpusManager.get_active_candidate_ids() for filtered corpus

### G. Materials domain bootstrap
- 12 real papers (HEAs, MXenes, MOFs, self-healing, quantum materials, etc.)
- 16 real findings with provenance quotes and confidence scores
- seed_materials() function in bootstrap_findings.py
- --domain materials and --domain all CLI flags

### H. Schema v005
- bt_diversity_context: per-run steering parameters
- bt_rotation_state: per-domain rotation state (domain PRIMARY KEY, upsert)
- bt_corpus_archive: archived candidate IDs with reason

### I. Metrics / observability
- DiversityContext persisted per run (inspectable via repo.get_diversity_context)
- Rotation state visible via repo.get_rotation_state
- Archive stats via CorpusManager.run_archival() return value

### J. Tests (test_phase4d.py)
- 58 tests covering all deliverables
- 0 failures

### K. Documentation
- This file (plan)
- BREAKTHROUGH_ENGINE_PHASE4D_STATUS.md (outcomes)
- BREAKTHROUGH_ENGINE_DIVERSITY_ENGINE.md (architecture reference)

## Constraints

- Do not loosen novelty thresholds
- Do not remove archived candidates from DB
- All tests offline-safe (no Ollama required)
- No architecture redesign
