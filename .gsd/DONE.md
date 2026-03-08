# GSD - Completed Tasks

## 2026-03-08 (Phase 4D)

- [x] Schema v005 migration (bt_diversity_context, bt_rotation_state, bt_corpus_archive)
- [x] 8 new Repository methods for v005 tables
- [x] DiversityEngine (build_context, advance_rotation, negative memory from blocked candidates)
- [x] DiversityContext dataclass (sub_domain, excluded_topics, focus_areas, rotation_policy)
- [x] build_diversity_prompt_addendum (LLM steering from context)
- [x] Sub-domain rotation (10 sub-domains per domain, every 2 runs)
- [x] CorpusManager (is_active, run_archival, archive_by_cluster, get_active_count)
- [x] Materials domain bootstrap: 12 papers, 16 findings (seed_materials())
- [x] domain_fit YAMLs extended with sub_domains field (clean-energy, materials)
- [x] DomainFitConfig.sub_domains field loaded from YAML
- [x] OllamaCandidateGenerator.generate() accepts diversity_context
- [x] All other generators updated: Fake, Demo, Benchmark
- [x] Orchestrator: builds diversity context before generation, advances rotation after run
- [x] 46 new tests (305 total, 0 failed)
- [x] Phase 4D documentation (3 new docs)

## 2026-03-07 (Phase 4C)

- [x] Review UI actions wired end-to-end (form + JSON, confirm dialogs)
- [x] Domain-fit config externalized to YAML (3 configs, no hardcoded keywords)
- [x] Embedding monitoring module (per-run stats, drift analysis)
- [x] Calibration diagnostics (per-run gate pass/fail stats)
- [x] DB migration v004 (2 new tables: bt_embedding_monitor, bt_calibration_diagnostics)
- [x] Candidate detail HTML view with score bars and trust signals
- [x] Active thresholds endpoint (/view/thresholds)
- [x] Embedding drift endpoint (/view/embedding-drift)
- [x] Live validation: 8 runs with nomic-embed-text (39 candidates, 35 blocked, 2 drafts)
- [x] Threshold assessment: all thresholds validated as correct
- [x] Model strategy doc updated for Phase 4C
- [x] 38 new tests (259 total, 0 failed)
- [x] Phase 4C documentation (6 new docs)

## 2026-03-07 (Phase 4B)

- [x] Preflight cleanup: fixed /no_think doc drift, model strategy accuracy
- [x] Domain-fit evaluator with keyword-based scoring (domain_fit.py)
- [x] Embedding novelty engine with MockEmbeddingProvider and OllamaEmbeddingProvider
- [x] Improved evidence linking with ranked fallback (retrieval.py rank_evidence)
- [x] Retrieval query construction (build_retrieval_query)
- [x] Publication gate diagnostic explanations and additional warnings
- [x] Gate diagnostics persistence (bt_gate_diagnostics table)
- [x] DB migration v003 (4 new tables)
- [x] Minimal operator review HTML view (/api/breakthrough/view/review)
- [x] Candidate detail JSON endpoint (/view/candidate/<id>)
- [x] Model strategy doc updated with embedding strategy
- [x] 45 new tests (221 total, 0 failed)
- [x] Phase 4B documentation (5 new docs)

## 2026-03-08 (Phase 4A)

- [x] Phase A: Freeze baseline (commit d5408ad, tag breakthrough-engine-phase3-calibrated)
- [x] Phase B: GSD integration (repo-local .gsd/ directory, documented)
- [x] Phase C: Model strategy (qwen3.5:9b-q4_K_M primary, llama3.1:8b fallback)
- [x] Phase D: Ollama readiness (server started, doctor command added)
- [x] Phase E: Evidence bootstrap (12 papers, 18 findings, clean-energy)
- [x] Phase F: 12 production_shadow runs (60 candidates, avg score 0.863)
- [x] Phase G: Tuning (think:false fix, shadow finalist marking)
- [x] Phase H: 3 production_review runs (3 drafts created, all pending)
- [x] Phase I: Tests (176 passed, 0 failed, 0 warnings)
- [x] Phase J: Final documentation and readiness report

## 2026-03-07 (Phase 3 Calibration)

- [x] Calibration runs (6 total: 3 demo_local, 1 shadow, 1 review, 1 saturated)
- [x] datetime.utcnow() deprecation fix (693 warnings → 0)
