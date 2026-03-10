# Phase 8 Plan: Reviewed Policy Learning, 10-Campaign Batch, Bounded Daily Automation

**Branch**: `breakthrough-engine-phase8-reviewed-learning`
**Base**: `breakthrough-engine-phase7d-eval-profile` @ `3381cca`
**Date**: 2026-03-09
**Status**: IN PROGRESS

---

## Objective

Turn the Breakthrough Engine into a trustworthy self-improving clean-energy discovery engine by:

1. Freezing Phase 7D as the new trusted reviewed baseline
2. Creating a reviewed policy-learning loop using clean human labels
3. Expanding to a 10-campaign reviewed clean-energy evaluation batch
4. Supporting champion/challenger promotion using benchmark + reviewed evidence
5. Adding bounded daily automation for one evaluation + one production campaign/day
6. Keeping everything explainable, auditable, and reversible

---

## Starting State (Phase 7D @ 3381cca)

| Field | Value |
|-------|-------|
| Branch | breakthrough-engine-phase7d-eval-profile |
| Commit | 3381cca |
| Tests | 614 passing, 0 failures |
| Schema version | v003 (eval), v002 (smoke/pilot) |
| Integrity failures | 0 |
| Generation model | qwen3.5:9b-q4_K_M |
| Embedding model | nomic-embed-text (OllamaEmbeddingProvider) |
| Champion policy | phase5_champion |
| Phase 5 baseline | runtime/baselines/phase5_validated_benchmark.json |
| Phase 7D baseline | NOT YET FROZEN (this phase creates it) |
| Review labels (Phase 7D batch) | 0 / expected 10+ (champions + runners-up) |
| DB migrations | 10 |

---

## Deliverables

| Deliverable | Description | Priority |
|-------------|-------------|----------|
| A | Phase 7D reviewed baseline freeze | 1 |
| B | Review-label completeness tooling | 1 |
| C | Reviewed policy promotion gate | 2 |
| D | Review-weighted Bayesian updates | 2 |
| E | 10-campaign reviewed clean-energy batch | 3 |
| F | Champion/challenger policy trials | 3 |
| G | Bounded daily automation profiles | 4 |
| H | Daily review queue integration | 4 |
| I | Tests | 5 |
| J | Branch / commit strategy | 5 |

---

## Constraints

1. Do not merge to main
2. Do not redesign the architecture
3. Do not weaken novelty thresholds
4. Do not remove integrity gating
5. Do not start full RL training
6. Keep at most 1–2 challengers at a time
7. All tests offline-safe
8. Preserve one-publication-per-run invariant
9. Preserve production embedding behavior
10. Keep policy changes explainable and rollback-safe

---

## Architecture Additions

### New Modules
- `breakthrough_engine/reviewed_baseline.py` — baseline registry + freeze helpers
- `breakthrough_engine/label_completeness.py` — missing-label detection + export
- `breakthrough_engine/daily_automation.py` — bounded daily runner + review queue
- `config/daily_profiles/evaluation_daily_clean_energy.yaml`
- `config/daily_profiles/production_daily_clean_energy.yaml`

### Extended Modules
- `breakthrough_engine/db.py` — migration 11: bt_reviewed_baselines, bt_review_queue, bt_daily_automation_runs
- `breakthrough_engine/policy_registry.py` — review-signal promotion gate, rolled_back state
- `breakthrough_engine/bayesian_evaluator.py` — review-label posterior updates
- `breakthrough_engine/cli.py` — new subcommands: baseline, label-completeness, daily, review-queue

### New Tests
- `tests/test_breakthrough/test_phase8.py`

---

## Key Design Decisions

### Two Trusted Baselines
- **Phase 5 frozen baseline**: `runtime/baselines/phase5_validated_benchmark.json`
  - Purpose: Long-term regression testing on core quality (deterministic benchmark)
  - When to use: Any promotion to full champion, ongoing regression checks
- **Phase 7D reviewed baseline**: `runtime/baselines/phase7d_reviewed_baseline.json`
  - Purpose: Review-signal policy-learning comparison
  - When to use: Reviewed batch comparisons, policy posterior anchoring

### Promotion States (Extended)
- `challenger` → `probationary_champion` → `champion` → (rollback) → `rolled_back`

### Daily Automation Bounds
- Max 1 evaluation campaign/day
- Max 1 production campaign/day
- Dry-run mode always available
- No unattended perpetual operation by default
