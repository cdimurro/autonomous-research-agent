# Phase 6 Plan: Daily Policy Optimization, Bayesian Evaluation, and Review Cockpit

## Status: IN PROGRESS

## Branch
`breakthrough-engine-phase6`

## Phase 5 Baseline
- Tag: `breakthrough-engine-phase5-validated`
- Commit: `29d68a39` (Phase 5 validated)
- Frozen baseline artifact: `runtime/baselines/phase5_validated_benchmark.json`

## Objective

Build on the validated Phase 5 system to make it improve over time:
1. A fixed benchmark harness for regression against the Phase 5 baseline
2. Bayesian posterior tracking over key quality signals
3. Champion/challenger policy framework
4. Quality-first daily search ladder
5. Fast falsification lane
6. Richer review cockpit
7. Reward logging for future RL

## Two Operating Modes

### BENCHMARK / REGRESSION MODE
- Fixed seed (42), fixed domain, fixed budgets
- FakeCandidateGenerator + MockEmbeddingProvider (offline-safe)
- Compares against `runtime/baselines/phase5_validated_benchmark.json`

### DAILY PRODUCTION SEARCH MODE
- Quality-first, larger compute budget
- Can run for hours
- 5-stage search ladder with stopping rules

## New Modules

| Module | Purpose |
|--------|---------|
| `policy_registry.py` | PolicyConfig, champion/challenger framework, promotion criteria |
| `bayesian_evaluator.py` | Beta-Binomial posteriors, correct observation units, Thompson sampling |
| `baseline_comparator.py` | Frozen baseline comparison harness |
| `falsification.py` | Rule-based contradiction/gap/weakness analysis |
| `reward_logger.py` | Reward signals + RL-ready trajectories with versioned recipes |
| `review_cockpit.py` | ReviewDecisionPacket builder + text/HTML output |
| `daily_search.py` | 5-stage ladder with per-stage budgets and stopping rules |

## Schema v007

9 new tables added to existing 26 (`bt_` prefix):
- `bt_policies`, `bt_policy_trials`, `bt_bayesian_posteriors`
- `bt_reward_logs`, `bt_trajectories`
- `bt_baseline_comparisons`, `bt_falsification_summaries`
- `bt_daily_campaigns`, `bt_ladder_stages`

## Key Design Decisions

1. **Frozen baseline**: Phase 5 baseline is a committed JSON artifact created from the validated tag. Never overwritten.
2. **Bayesian units**: Each metric has an explicit observation unit (candidate/run/draft). Posteriors update at the correct granularity.
3. **Two-stage promotion**: Challenger → Probation → Champion. Conjunctive multi-metric gate.
4. **Versioned reward recipes**: Reward weights in config, not hardcode.
5. **Per-stage stopping rules**: Each ladder stage has `max_trials`, `min_score_to_advance`, `max_wall_clock_seconds`, `abandon_floor`.

## Acceptance Criteria

- [ ] Benchmark harness comparing against Phase 5 baseline
- [ ] Bayesian evaluation engine with persisted posteriors (correct units)
- [ ] Champion/challenger policy experimentation with two-stage promotion
- [ ] Quality-first daily search ladder with stopping rules
- [ ] Falsification summary lane
- [ ] Richer review decision packet
- [ ] RL-ready reward logs with versioned recipes
- [ ] Bounded validation showing measurable comparison against baseline
- [ ] All 369 existing tests still pass
- [ ] New Phase 6 tests added and passing
