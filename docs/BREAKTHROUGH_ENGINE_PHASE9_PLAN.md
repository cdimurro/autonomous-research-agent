# Phase 9 Plan: Policy Actuation, Reviewed A/B Learning, and Autonomous Improvement Prep

**Branch**: `breakthrough-engine-phase9-policy-actuation`
**Base**: `breakthrough-engine-phase8b-reviewed-loop` @ `1b52a0f`
**Date**: 2026-03-10
**Champion**: `phase5_champion`
**Challenger**: `synthesis_focus_v1`

---

## Current State (Phase 8B Complete)

| Item | Value |
|------|-------|
| Branch | breakthrough-engine-phase8b-reviewed-loop |
| Commit | 1b52a0f |
| Tests | 734 passing, 0 failures |
| Champion policy ID | phase5_champion |
| Challenger policy ID | synthesis_focus_v1 (ba0cb255c20f4995) |
| Schema version | v003 |
| Phase 8B trial result | insufficient_evidence (3+3 campaigns) |
| Phase 8 baseline | phase8_reviewed_baseline.json (10 campaigns, mean score 0.91192) |
| Review labels | 20 total: 14 approve, 0 reject, 6 defer |

---

## Phase 9 Objectives

### Priority 1: Policy Actuation Audit + Wiring
- Audit all policy-configurable surfaces
- Classify: fully actuated / partially actuated / inert
- Wire inert surfaces into runtime

### Priority 2: Reviewed A/B Trial Framework Hardening
- Improve per-arm reporting
- Explicit arm assignment and balance
- Better batch summary export

### Priority 3: Autonomous Daily Operation Prep
- Champion-only production automation
- Safe evidence accumulation
- Bounded launch commands

### Priority 4: Extended Reviewed A/B Batch
- 6+ campaigns per arm (12+ total)
- Promotion readiness assessment

### Priority 5: Tests + Docs + Final Status

---

## Key Constraints

1. Do NOT merge to main
2. Do NOT redesign architecture
3. Keep exactly ONE active challenger (synthesis_focus_v1)
4. Keep automatic promotion OFF
5. Keep all tests offline-safe
6. Preserve one-publication-per-run invariant
7. Preserve production embeddings
8. Preserve evaluation-grade integrity gating
9. Champion-only for autonomous production
10. All policy effects must be explicit, logged, and reversible

---

## Known Inert Policy Surfaces (Phase 8B)

Based on code audit before Phase 9:

| Surface | Status | Location |
|---------|--------|----------|
| generation_prompt_variant | INERT — system prompt never switches | candidate_generator.py |
| scoring_weights | WIRED — via _apply_policy() in daily_search.py | daily_search.py, scoring.py |
| diversity_steering_variant | INERT — no variant logic implemented | diversity.py |
| evidence_ranking_weights | INERT — rank_evidence() uses hardcoded weights | retrieval.py |
| negative_memory_strategy | INERT — not used in memory module | memory.py |
| sub_domain_rotation_policy | PARTIALLY WIRED — DiversityEngine.build_context() accepts it but orchestrator ignores policy value | orchestrator.py, diversity.py |
| bridge_selection_policy | INERT — synthesis always uses auto | synthesis.py |
| review_gating_heuristics | INERT — no runtime use | - |

## Phase 9 Actuation Deliverables

### D-A: Wire generation_prompt_variant
- Add CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS to candidate_generator.py
- Add PROMPT_VARIANTS dict
- OllamaCandidateGenerator accepts prompt_variant in __init__
- Orchestrator passes policy_config to generator construction
- FakeCandidateGenerator stores prompt_variant for test inspection

### D-B: Wire evidence_ranking_weights
- Add evidence_ranking_weights parameter to rank_evidence()
- Orchestrator passes policy_config.evidence_ranking_weights when available

### D-C: Wire sub_domain_rotation_policy
- Orchestrator passes policy_config.sub_domain_rotation_policy to diversity_engine.build_context()

### D-D: Policy snapshot logging per run
- Orchestrator logs effective policy id and key parameters at run start

### D-E: Pass policy_config to orchestrator from daily_search
- daily_search._run_single_trial() passes policy_config=policy to BreakthroughOrchestrator

---

## Deferred to Future Phases

- negative_memory_strategy (RunMemory module changes needed)
- diversity_steering_variant (needs DiversityEngine internal changes)
- bridge_selection_policy (synthesis module changes needed)
- Automatic promotion
- Full RL training
- Multiple challengers
