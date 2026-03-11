# Phase 9 Status: Policy Actuation, Reviewed A/B Learning, and Autonomous Improvement Prep

**Branch**: `breakthrough-engine-phase9-policy-actuation`
**Base**: `breakthrough-engine-phase8b-reviewed-loop` @ `1b52a0f`
**Date**: 2026-03-10
**Status**: IMPLEMENTATION COMPLETE

---

## Summary

Phase 9 delivers real policy actuation through the runtime pipeline. The champion/challenger framework now tests genuine behavioral differences, not just infrastructure scaffolding.

---

## What Was Done

### Deliverable A: Policy Actuation Audit ✅
- Audited all 8 policy-configurable surfaces
- Classified: 1 fully wired (Phase 8B), 3 newly wired (Phase 9), 4 deferred
- Documented in `docs/BREAKTHROUGH_ENGINE_POLICY_ACTUATION.md`

### Deliverable B: generation_prompt_variant Actuation ✅
**File**: `breakthrough_engine/candidate_generator.py`

Added:
- `CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS` — emphasizes mechanism plausibility, testability clarity, and cross-domain synthesis
- `CANDIDATE_GENERATION_PROMPT_EVIDENCE_HEAVY` — emphasizes evidence grounding and conservative extrapolation
- `PROMPT_VARIANTS` dict mapping variant names to templates
- `OllamaCandidateGenerator(prompt_variant=...)` — selects system prompt from PROMPT_VARIANTS
- `FakeCandidateGenerator(prompt_variant=...)` — stores variant for test inspection
- `DemoCandidateGenerator(prompt_variant=...)` — propagates variant

**Effect**: When `synthesis_focus_v1` challenger runs, the LLM is instructed to prioritize mechanism clarity and testability, consistent with the plausibility-weighted scoring.

### Deliverable C: Scoring Weight Actuation ✅ (confirmed wired Phase 8B)
**File**: `breakthrough_engine/daily_search.py`

`_apply_policy()` already correctly overrides `ResearchProgram.scoring_weights` from `PolicyConfig.scoring_weights`. Confirmed working through audit and test suite.

### Deliverable D: evidence_ranking_weights Actuation ✅
**File**: `breakthrough_engine/retrieval.py`

`rank_evidence()` now accepts `evidence_ranking_weights: dict | None` parameter. When provided, overrides hardcoded layer weights (api_relevance, domain_overlap, mechanism_overlap, baseline).

### Deliverable E: sub_domain_rotation_policy Actuation ✅
**File**: `breakthrough_engine/orchestrator.py`

`_execute_cycle()` now reads `self.policy_config.sub_domain_rotation_policy` and passes it to `diversity_engine.build_context(rotation_policy=...)`.

### Deliverable F: policy_config Threading ✅
**Files**: `breakthrough_engine/orchestrator.py`, `breakthrough_engine/daily_search.py`

- `BreakthroughOrchestrator.__init__()` now accepts `policy_config=` parameter
- Stores as `self.policy_config`
- Sets `self.policy_id` from config if not separately provided
- Constructs generator with `prompt_variant` from config
- `daily_search.DailySearchLadder._run_single_trial()` now passes `policy_config=policy` to orchestrator in production mode

### Deliverable G: Policy Snapshot Logging ✅
**File**: `breakthrough_engine/orchestrator.py`

At start of each `_execute_cycle()`, logs:
```
Policy snapshot: id=<id> generation_prompt_variant=<v> scoring_weights=<w> evidence_ranking_weights=<w> sub_domain_rotation_policy=<p>
```

---

## Test Results

| Suite | Before Phase 9 | After Phase 9 |
|-------|---------------|---------------|
| Existing tests | 734 passing | 734 passing |
| Phase 9 new tests | 0 | 45 |
| **Total** | **734** | **779** |
| Failures | 0 | 0 |

**New test file**: `tests/test_breakthrough/test_phase9.py` (45 tests)

Test coverage:
- Prompt variant constants and registry
- FakeCandidateGenerator prompt_variant storage
- DemoCandidateGenerator prompt_variant propagation
- OllamaCandidateGenerator prompt_variant initialization and fallback
- Orchestrator policy_config wiring
- Scoring weight actuation and ranking divergence
- Evidence ranking weight parameter
- PolicyConfig integration with _apply_policy
- End-to-end offline runs with both champion and challenger policies
- Policy actuation audit assertions

---

## Actuation Matrix (Final)

| Surface | Status |
|---------|--------|
| scoring_weights | WIRED (Phase 8B) |
| generation_prompt_variant | **WIRED (Phase 9)** |
| evidence_ranking_weights | **WIRED (Phase 9)** |
| sub_domain_rotation_policy | **WIRED (Phase 9)** |
| diversity_steering_variant | DEFERRED (Phase 10) |
| negative_memory_strategy | DEFERRED (Phase 10) |
| bridge_selection_policy | DEFERRED (Phase 10) |
| review_gating_heuristics | DEFERRED (Phase 10) |

---

## synthesis_focus_v1 Behavioral Differences (Now Real)

| Dimension | Champion | Challenger | Delta |
|-----------|----------|------------|-------|
| LLM system prompt | standard rules | synthesis_focus: mechanism-first, testability emphasis | Qualitative |
| scoring: novelty weight | 0.20 | 0.18 | -10% |
| scoring: plausibility weight | 0.20 | 0.25 | +25% |
| scoring: simulation_readiness | 0.10 | 0.12 | +20% |
| scoring: inverse_validation_cost | 0.10 | 0.05 | -50% |
| evidence_ranking_weights | defaults | None (same as champion) | No change |
| sub_domain_rotation_policy | "auto" | "auto" | No change |

**Challenger hypothesis**: "Instructing the LLM to emphasize mechanism plausibility and weighting plausibility/testability higher in scoring produces candidates that reviewers approve at higher rates."

---

## Deferred Deliverables (Phase 10)

- Extended reviewed A/B batch (6+ campaigns per arm) — requires production LLM availability
- Review-weighted promotion readiness assessment — requires reviewed batch data
- Autonomous daily operation prep runbook extension
- Cumulative learning summary artifact

These deliverables require actual LLM campaigns which cannot run offline. The infrastructure is ready; the operator should run batches using the now-actuated policy wiring.

---

## Launch Commands for Extended A/B Batch

```bash
# Health check first
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy

# Champion arm campaigns (repeat 6x on separate days or separate profiles)
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Challenger arm campaigns
python -m breakthrough_engine ds run eval_clean_energy_30m --policy synthesis_focus_v1

# Build trial comparison after 6+ per arm
python -m breakthrough_engine challenger-trial build \
  --champion-campaigns <id1,id2,...> \
  --challenger-id synthesis_focus_v1

# Export trial summary
python -m breakthrough_engine challenger-trial export --trial-id <trial_id>
```

---

## Rollback Safety

Policy actuation is reversible:
- If synthesis_focus_v1 shows regression: run `python -m breakthrough_engine policy rollback --reason "regression detected"`
- Generator reverts to standard prompt automatically when champion is phase5_champion
- No DB migrations needed for rollback
- All policy snapshots logged per run for audit trail
