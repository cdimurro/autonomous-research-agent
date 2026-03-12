# Phase 10: Next Challenger Design Preparation

**Phase**: 10 (design only — not yet activated)
**Date prepared**: 2026-03-12
**Current champion**: `evidence_diversity_v1`
**Baseline anchor**: `phase9e_promoted_production_regime2`
**Status**: DESIGN PREP ONLY — no registration, no trial

---

## Available Challenger Surfaces

From the Policy Actuation Matrix (Phase 9):

| Surface | Status |
|---------|--------|
| scoring_weights | WIRED — trialed (phase9b, RETIRED_FAILED) |
| generation_prompt_variant | WIRED — trialed (phase9b, RETIRED_FAILED as part of synthesis_focus_v1) |
| evidence_ranking_weights | WIRED — **trialed and PROMOTED** (evidence_diversity_v1) |
| sub_domain_rotation_policy | WIRED — not yet trialed |
| diversity_steering_variant | WIRED — not yet trialed |
| negative_memory_strategy | WIRED — not yet trialed |
| bridge_selection_policy | WIRED — not yet trialed |

---

## Selection: diversity_steering_variant

**Recommended next challenger surface: `diversity_steering_variant`**

### Rationale

**Why diversity_steering_variant over negative_memory_strategy:**

1. **Mechanism hypothesis is clearer.** The Phase 9B/9D lessons establish that mechanism-level changes (evidence ranking, prompt focus) have cleaner cause-effect chains than retrieval-level changes. `diversity_steering_variant` directly controls how diverse the candidate generation space is — a well-understood lever with directional prediction.

2. **Complementarity with evidence_diversity_v1.** The current champion improves evidence selection (better mechanistic grounding at the input stage). `diversity_steering_variant` operates at the generation diversity stage — potentially reducing topic repetition within a session without affecting evidence quality. These are orthogonal surfaces.

3. **Negative memory strategy is higher-risk.** `negative_memory_strategy` affects what topics the system avoids, which could interact with evidence_ranking_weights in complex ways. As the second test of the promoted champion, we want the cleanest possible intervention. Negative memory will be a better Phase 11 surface once we understand diversity steering behavior.

4. **Deferred too long.** Three deferred surfaces remain. `diversity_steering_variant` has the most direct mechanistic interpretation and the lowest risk of interactions with the current champion's evidence ranking change.

---

## Challenger Design: diversity_steering_v1

### Single Surface Change

| Surface | Champion (evidence_diversity_v1) | Challenger (diversity_steering_v1) |
|---------|----------------------------------|-------------------------------------|
| `diversity_steering_variant` | `standard` | `aggressive` |
| All other surfaces | unchanged | unchanged |

### Hypothesis

Switching from `standard` to `aggressive` diversity steering will reduce within-session topic repetition, producing more topically distinct finalist pools. This should:

1. Reduce "topic clustering" where multiple finalists converge on the same mechanism family (e.g., three different NiFe-LDH candidates in the same campaign)
2. Improve campaign-level novelty diversity without reducing per-candidate novelty
3. Potentially improve runner-up approval rate by ensuring finalists cover different topical spaces

**Predicted direction:**
- Novelty confidence: neutral or +small (more diverse topics = less risk of "I've seen this before" reviewer reaction)
- Technical plausibility: neutral (mechanism quality unchanged — evidence_ranking_weights still in effect)
- Approval rate: neutral to +small (more diverse pool may reduce risk that all candidates fail for the same reason)
- Score: neutral (scoring weights unchanged)

### Failure Hypothesis (for falsification)

If `aggressive` steering causes over-diversification, it may produce candidates with weaker mechanistic coherence (because the system is forced to generate across distant topic areas). In this case:
- Plausibility would decline (ideas forced beyond natural evidence support)
- Runner-up quality may decline (diversity at the cost of depth)

This is a testable prediction: if we see plausibility delta < -0.05 and runner-up approval decline, aggressive steering is too much.

---

## Challenger Config Template

**Do not activate yet.** For documentation only.

```json
{
  "name": "diversity_steering_v1",
  "version": "1.0",
  "description": "Phase 10 challenger: diversity_steering_variant=aggressive. Single-surface change from evidence_diversity_v1: diversity steering increased from standard to aggressive. Hypothesis: reduces within-session topic clustering and improves finalist pool diversity without sacrificing mechanism quality. Evidence ranking, prompt, and scoring unchanged from current champion.",
  "generation_prompt_variant": "standard",
  "diversity_steering_variant": "aggressive",
  "sub_domain_rotation_policy": "auto",
  "bridge_selection_policy": "auto",
  "evidence_ranking_weights": {
    "api_relevance": 0.20,
    "domain_overlap": 0.30,
    "mechanism_overlap": 0.35,
    "baseline": 0.15
  },
  "negative_memory_strategy": "standard",
  "review_gating_heuristics": [],
  "scoring_weights": null,
  "metadata": {
    "phase": "10",
    "challenger_vs": "evidence_diversity_v1",
    "predecessor": "evidence_diversity_v1",
    "predecessor_verdict": "PROMOTION_RECOMMENDED",
    "hypothesis": "Aggressive diversity steering reduces finalist topic clustering without sacrificing mechanism quality",
    "config_diff": {
      "diversity_steering_variant": "standard (champion) -> aggressive"
    },
    "unchanged_vs_champion": [
      "generation_prompt_variant",
      "scoring_weights",
      "evidence_ranking_weights",
      "sub_domain_rotation_policy",
      "bridge_selection_policy",
      "negative_memory_strategy"
    ]
  }
}
```

---

## Pre-Registration Checklist (Before Phase 10 Activation)

- [ ] Verify `diversity_steering_variant="aggressive"` is wired through in `diversity_engine.build_context()`
- [ ] Confirm `aggressive` variant produces different finalist pools in dry-run vs `standard`
- [ ] Create proof-of-actuation artifact: controlled set with both variants, compare finalist diversity
- [ ] Confirm the new `phase9e_promoted_production_baseline_regime2` is the A/B anchor
- [ ] Register challenger: `python -m breakthrough_engine policy register --name diversity_steering_v1 --config-path config/policies/diversity_steering_v1.json`
- [ ] Create `docs/BREAKTHROUGH_ENGINE_PHASE10_PLAN.md`

---

## Alternative Consideration: negative_memory_strategy

If `diversity_steering_variant` is not ready (e.g., `aggressive` variant not yet implemented), the alternative is `negative_memory_strategy`.

**negative_memory_v1** design concept:
- Change: `negative_memory_strategy = "strict"` (avoid topics with repeated defer/reject labels)
- Hypothesis: strict negative memory reduces generation of ideas too similar to prior deferrals, improving approval rate floor
- Risk: may over-suppress topics that were deferred for reasons specific to one session
- Interaction risk with evidence_diversity_v1: medium (negative memory affects topic selection, evidence ranking affects evidence selection — both at different pipeline stages)

This remains a Phase 11 option if Phase 10 diversity_steering trial is inconclusive.

---

## Phase 10 Trial Plan (When Ready)

```bash
# Check diversity_steering wiring is live
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy --policy diversity_steering_v1

# Compare finalist diversity (manual inspection)
# If actuation is confirmed, register and run 6+6 trial:

# Champion arm (6 campaigns):
python -m breakthrough_engine ds run eval_clean_energy_30m

# Challenger arm (6 campaigns):
python -m breakthrough_engine ds run eval_clean_energy_30m --policy diversity_steering_v1

# Compare against phase9e_promoted_production_regime2 baseline
```

**Promotion gates** (same as Phase 9D, anchored to evidence_diversity_v1 baseline):
- Score delta ≥ -0.03 vs evidence_diversity_v1 mean (0.9126)
- Approval rate delta ≥ -5pp vs evidence_diversity_v1 rate (83.3%)
- Novelty confidence delta ≥ -0.05 vs evidence_diversity_v1 (0.853)
- Technical plausibility delta ≥ -0.05 vs evidence_diversity_v1 (0.855)
