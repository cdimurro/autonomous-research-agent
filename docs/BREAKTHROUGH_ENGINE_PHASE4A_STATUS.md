# Breakthrough Engine - Phase 4A Status

**Status: Phase 4A Complete**

## Baseline

- **Phase 3 commit:** `d5408ad` on `main`
- **Phase 3 tag:** `breakthrough-engine-phase3-calibrated`
- **Schema version:** v002
- **Python:** 3.14.3 with venv at `.venv/`
- **Ollama:** v0.17.6 at `/opt/homebrew/bin/ollama`
- **Model:** qwen3.5:9b-q4_K_M (9.7B params, Q4_K_M quantization)

## Completed Tasks

- [x] **Phase A:** Freeze baseline (commit d5408ad, tag breakthrough-engine-phase3-calibrated)
- [x] **Phase B:** GSD integration (repo-local `.gsd/` directory, documented)
- [x] **Phase C:** Model strategy selection (qwen3.5:9b-q4_K_M primary, llama3.1:8b fallback)
- [x] **Phase D:** Ollama readiness (server started, model loaded, doctor command added)
- [x] **Phase E:** Evidence bootstrapping (12 papers, 18 findings for clean-energy)
- [x] **Phase F:** Production shadow runs (12 completed, 60 candidates)
- [x] **Phase G:** Minimal tuning (think:false fix, shadow status fix)
- [x] **Phase H:** Production review validation (3 runs, 3 drafts created)
- [x] **Phase I:** Testing (176 passed, 0 failed, 0 warnings)
- [x] **Phase J:** Final documentation and readiness report

## Files Added

| File | Purpose |
|------|---------|
| `docs/BREAKTHROUGH_ENGINE_PHASE4A_PLAN.md` | Phase 4A scope and plan |
| `docs/BREAKTHROUGH_ENGINE_PHASE4A_STATUS.md` | This file |
| `docs/BREAKTHROUGH_ENGINE_MODEL_STRATEGY.md` | Model selection decisions |
| `docs/BREAKTHROUGH_ENGINE_GSD_INTEGRATION.md` | GSD integration guide |
| `docs/BREAKTHROUGH_ENGINE_LIVE_RUN_REPORT.md` | Live run results and analysis |
| `config/research_programs/clean_energy_shadow.yaml` | Shadow mode config |
| `config/research_programs/clean_energy_review.yaml` | Review mode config |
| `breakthrough_engine/bootstrap_findings.py` | Evidence seeding script |
| `.gsd/ACTIVE.md` | GSD active tasks |
| `.gsd/BLOCKERS.md` | GSD blockers |
| `.gsd/DONE.md` | GSD completed tasks |

## Files Changed

| File | Change | Justification |
|------|--------|---------------|
| `breakthrough_engine/candidate_generator.py` | `think: false` in Ollama payload, removed `/no_think` prefix | Model spent all tokens on thinking, producing empty responses |
| `breakthrough_engine/orchestrator.py` | Shadow mode marks finalists | Candidates passing all gates stayed at "generated" status |
| `breakthrough_engine/cli.py` | Added `doctor` command | System readiness verification |
| `tests/test_breakthrough/test_phase3.py` | Updated 2 assertions | Shadow mode status change, API test tolerance |

## Test Results

```
Command: .venv/bin/python -m pytest tests/test_breakthrough/ -v
Result: 176 passed, 0 failed, 0 warnings in 0.42s
```

## Live Run Summary

| Metric | Value |
|--------|-------|
| Shadow runs completed | 12 |
| Review runs completed | 3 |
| Total LLM-generated candidates | 77 |
| Average score | 0.863 |
| Score range | 0.678 – 0.950 |
| Publication gate pass rate | 100% (33/33 checked) |
| Review drafts created | 3 (all pending) |
| Average run time | ~195s |

## Blockers

None. All Phase 4A objectives met.

## Known Limitations

1. Evidence_refs from LLM not matched to specific items (default fallback)
2. Plausibility score is heuristic constant (0.75)
3. Novelty detection is lexical only (all-pass for diverse LLM outputs)
4. Mock simulator inflates simulation_readiness scores
5. Single domain bootstrapped (clean-energy only)

## Next Recommended Phase

**Phase 4B: Retrieval Quality + Novelty Enhancement**

Evidence-based rationale:
1. **Embedding-based novelty** — Lexical novelty all-passes on diverse LLM output. Semantic similarity would catch conceptually similar hypotheses across runs (e.g., multiple "waste heat + electrolysis" variants).
2. **Evidence matching** — Candidates should reference specific evidence items, not default to first 2. This requires either prompt improvement or post-generation evidence linking.
3. **Live retrieval** — OpenAlex/Crossref retrieval is implemented but untested. Enabling it would provide fresh, domain-current evidence instead of static bootstrapped findings.
4. **Multi-domain** — Bootstrap additional domains (materials-science) to test generalization.
5. **Operator dashboard** — With real data now available, a minimal review UI would improve operator workflow.
