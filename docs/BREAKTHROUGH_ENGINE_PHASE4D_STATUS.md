# Phase 4D Status: Diversity-Aware Generation

## Status: Implementation Complete — Awaiting Live Validation

## What Was Built

### New Files
| File | Description |
|------|-------------|
| `breakthrough_engine/diversity.py` | DiversityEngine, DiversityContext, build_diversity_prompt_addendum |
| `breakthrough_engine/corpus_manager.py` | CorpusManager: active/archived corpus management |
| `tests/test_breakthrough/test_phase4d.py` | 58 tests (0 failed) |
| `docs/BREAKTHROUGH_ENGINE_PHASE4D_PLAN.md` | Plan document |
| `docs/BREAKTHROUGH_ENGINE_DIVERSITY_ENGINE.md` | Architecture reference |
| `docs/BREAKTHROUGH_ENGINE_PHASE4D_STATUS.md` | This file |

### Modified Files
| File | Change |
|------|--------|
| `breakthrough_engine/db.py` | Added `_utcnow()`, v005 migration (3 tables), 8 new Repository methods |
| `breakthrough_engine/domain_fit.py` | Added `sub_domains` field to `DomainFitConfig`, loaded from YAML |
| `breakthrough_engine/candidate_generator.py` | Added `diversity_context` parameter to all generators |
| `breakthrough_engine/orchestrator.py` | Imports DiversityEngine + CorpusManager, builds context before generation, advances rotation after run |
| `breakthrough_engine/benchmark.py` | Added `diversity_context` parameter to BenchmarkCandidateGenerator |
| `breakthrough_engine/bootstrap_findings.py` | Added 12 materials papers, 16 findings, seed_materials(), updated main() |
| `config/domain_fit/clean_energy.yaml` | Added sub_domains list (10 sub-domains) |
| `config/domain_fit/materials.yaml` | Added sub_domains list (10 sub-domains) |
| `tests/test_breakthrough/test_phase4c.py` | Fixed schema version assertion: == 4 → >= 4 |

## Test Results

```
305 passed in 6.65s (0 failed, 0 warnings)
```

Previous: 259 tests. Phase 4D: +46 new tests.

## Schema Migration

v005 adds 3 tables:
- `bt_diversity_context`: per-run steering context
- `bt_rotation_state`: per-domain sub-domain rotation state
- `bt_corpus_archive`: archived candidate IDs

## What's Not Done Yet

- **Live validation**: No real Ollama runs yet for Phase 4D. Validation script pending.
- **Corpus archival in orchestrator**: CorpusManager exists but `run_archival()` is not called from orchestrator yet — safe to add as separate step.
- **Embedding scope**: NoveltyEngine still compares against all candidates, not filtered by corpus archive. Filtering via `get_active_candidate_ids()` is available but not wired in.

## Expected Production Behavior

With diversity context active:
1. Each run targets a specific sub-domain (rotating through 10)
2. Topics from prior blocked candidates are excluded from generation
3. LLM is directed to specific focus areas within the sub-domain
4. Novelty thresholds remain unchanged

Expected result: 30-60% reduction in novelty block rate (from 90%) over 8-12 runs.
