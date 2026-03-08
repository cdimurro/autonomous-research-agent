# GSD - Active Tasks

## Phase 4D: Implementation Complete — Live Validation Pending

All Phase 4D code tasks completed. See docs/BREAKTHROUGH_ENGINE_PHASE4D_STATUS.md.

## Remaining: Phase 4D Live Validation

- [ ] Run materials domain bootstrap against scires.db (python -m breakthrough_engine.bootstrap_findings --domain all)
- [ ] Run 4+ production_shadow runs in clean-energy with diversity context active
- [ ] Run 2+ production_shadow runs in materials domain
- [ ] Record block rates vs Phase 4C baseline (was 90%)
- [ ] Document results in BREAKTHROUGH_ENGINE_PHASE4D_LIVE_VALIDATION.md

## Optional Next Steps

- [ ] Wire CorpusManager.run_archival() into orchestrator end-of-run
- [ ] Wire NoveltyEngine to skip archived candidates (use get_active_candidate_ids)
- [ ] Begin Omniverse stub integration for real simulations
