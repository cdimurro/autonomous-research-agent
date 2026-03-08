# Breakthrough Engine - Phase 4A Plan

## Objective

Make the system operational for real local production_shadow and production_review cycles by:
1. Freezing the Phase 3 calibration baseline
2. Integrating GSD task tracking
3. Selecting a model strategy
4. Validating the Ollama generation path
5. Bootstrapping real findings for clean-energy domain
6. Running 10+ real production_shadow cycles
7. Applying minimal tuning based on observed failures
8. Validating production_review with real drafts
9. Producing a final readiness report

## Scope

- **Domain:** clean-energy (single domain bootstrap)
- **Model:** qwen3.5:9b-q4_K_M via local Ollama
- **Mode:** production_shadow first, then production_review
- **Changes allowed:** small tuning fixes justified by observed live-run behavior
- **Not allowed:** architecture redesign, embedding novelty, live Omniverse, large frontend

## Prerequisites

- Phase 3 complete (176 tests, 0 warnings)
- Ollama installed with qwen3.5:9b-q4_K_M model
- scires.db bootstrapped with clean-energy findings

## Deliverables

1. `docs/BREAKTHROUGH_ENGINE_PHASE4A_PLAN.md` (this file)
2. `docs/BREAKTHROUGH_ENGINE_PHASE4A_STATUS.md`
3. `docs/BREAKTHROUGH_ENGINE_MODEL_STRATEGY.md`
4. `docs/BREAKTHROUGH_ENGINE_GSD_INTEGRATION.md`
5. `docs/BREAKTHROUGH_ENGINE_LIVE_RUN_REPORT.md`
6. Production shadow/review program configs
7. `doctor` CLI command for readiness checks
8. `bootstrap_findings.py` for evidence seeding
9. Evidence-driven tuning changes
10. Final readiness assessment

## Constraints

1. No architecture redesign
2. No embedding novelty
3. No live Omniverse
4. No auto-approval of drafts
5. One publication per run invariant preserved
6. All tests remain offline-safe
7. All existing test/demo/deterministic modes preserved
