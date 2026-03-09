# Policy Optimization Lab

## Overview

A policy is a named set of configurable runtime choices. The policy registry tracks the current champion, challenger candidates, and trial history. Policy changes are data-driven and reversible.

## What is a Policy?

A policy defines:

| Parameter | Options | Effect |
|-----------|---------|--------|
| `generation_prompt_variant` | standard, synthesis_focus, evidence_heavy | LLM prompt addendum |
| `diversity_steering_variant` | standard, aggressive, conservative | How strongly diversity topics are excluded |
| `sub_domain_rotation_policy` | auto, fixed, random | Sub-domain selection strategy |
| `bridge_selection_policy` | auto, fixed, random | Bridge mechanism selection |
| `evidence_ranking_weights` | dict or None (default) | How evidence is ranked |
| `negative_memory_strategy` | standard, strict, permissive | How blocked topics are excluded |
| `scoring_weights` | dict or None (default) | How candidates are scored |

## Default Champion Policy

Represents validated Phase 5 behavior. All parameters use their defaults.
Seeded on first init. Policy ID: `"phase5_champion"`.

## Promotion Model (Two-Stage)

### Stage 1: Probation
Challenger is promoted to probation if it meets ALL of:
- Minimum 5 trial samples per domain pair
- novelty_pass posterior mean >= champion mean - 0.05
- top_candidate_final_score mean >= champion mean - 0.03
- falsification_pass_rate mean >= champion mean - 0.05
- operator_burden_proxy mean <= champion mean + 0.05 (lower is better)
- draft_quality_proxy mean >= champion mean - 0.03

This is a **conjunctive** gate — all criteria must be met.

### Stage 2: Full Champion
Probation policy becomes full champion if:
1. Passes a benchmark comparison run vs Phase 5 frozen baseline
2. No regression on any key metric > 0.05
3. Survives N=3 additional production runs without rollback trigger

### Rollback Trigger
Champion rolls back to previous if a benchmark comparison shows regression > 0.05 on any key metric vs the Phase 5 baseline.

## Trial History

Every policy trial is recorded in `bt_policy_trials`:
```
trial_type: "benchmark" | "production" | "challenger_eval"
outcome: "champion_improved" | "champion_maintained" | "challenger_failed"
```

## Policy Registry Methods

```python
registry = PolicyRegistry(repo)

# Register a challenger
challenger = registry.register(PolicyConfig(
    name="synthesis_focus_challenger",
    version="1.0",
    description="Increased synthesis focus in prompts",
    generation_prompt_variant="synthesis_focus",
))

# Get current champion
champion = registry.get_champion()

# Try promotion (checks all criteria)
promoted = registry.promote_challenger(
    challenger.id,
    evidence={"posterior_summary": {...}, "benchmark_comparison": {...}}
)

# Rollback if needed
registry.rollback_champion(reason="benchmark regression detected")

# View trial history
history = registry.get_trial_history(policy_id=challenger.id)
```

## Audit Trail

All champion/probation/rollback transitions are recorded with timestamp and reason. The `bt_policies` table preserves `previous_champion_id` for full lineage tracking.
