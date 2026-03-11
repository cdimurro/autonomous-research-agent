# Phase 9D Readiness Package: evidence_diversity_v1 A/B Trial

**Phase**: 9D (upcoming)
**Branch**: `breakthrough-engine-phase9c-challenger-iteration` (or new branch)
**Status**: READY TO PREPARE — awaiting Phase 9C-B baseline freeze
**Date**: 2026-03-11

---

## Prerequisites (Must Be Complete Before Launching Phase 9D)

| Prerequisite | Status |
|-------------|--------|
| Phase 9C-B eval daily collection (3 runs) | COMPLETE |
| Phase 9C-B production daily collection (3 runs) | PENDING (in progress) |
| Phase 9C-B review labels (12+) | PENDING |
| Phase 9C-B Regime 2 operational baseline frozen | PENDING |
| evidence_diversity_v1 registered in DB | COMPLETE (id=3f24a0a2a8074759) |
| evidence_ranking_weights verified in DB | COMPLETE |
| Proof of actuation verified | COMPLETE |
| synthesis_focus_v1 retired | COMPLETE |

---

## A/B Trial Configuration

| Parameter | Value |
|-----------|-------|
| Trial ID | `phase9c_ab_trial` |
| Profile | `eval_clean_energy_30m` |
| Champion arm | `phase5_champion` |
| Challenger arm | `evidence_diversity_v1` |
| Campaigns per arm | 6 (minimum) |
| Total campaigns | 12 |
| Labels per campaign | 2 (champion + 1 runner-up) |
| Total label target | 24 |
| Embedding regime | Regime 2 (qwen3-embedding:4b) — mandatory |
| Promotion | Manual only — all 4 gates must pass |

---

## Champion Arm Launch Command

```bash
BT_EMBEDDING_MODEL=qwen3-embedding:4b \
  python -m breakthrough_engine ds run eval_clean_energy_30m
```

Or with daily automation (no --policy flag = champion):

```bash
BT_EMBEDDING_MODEL=qwen3-embedding:4b \
  python -m breakthrough_engine daily run evaluation_daily_clean_energy [--force]
```

## Challenger Arm Launch Command

```bash
BT_EMBEDDING_MODEL=qwen3-embedding:4b \
  python -m breakthrough_engine ds run eval_clean_energy_30m --policy evidence_diversity_v1
```

---

## Promotion Gates (All Must Pass)

| Gate | Threshold | Description |
|------|-----------|-------------|
| score_delta | ≥ -0.03 | challenger mean score ≥ champion mean - 0.03 |
| approval_rate_delta | ≥ -0.05 | challenger approval rate ≥ champion rate - 5pp |
| novelty_confidence_delta | ≥ -0.05 | challenger novelty ≥ champion novelty - 0.05 |
| technical_plausibility_delta | ≥ -0.05 | challenger plausibility ≥ champion plausibility - 0.05 |

**Pass condition**: ALL four gates must pass simultaneously.

---

## Expected Baseline Values (Phase 9C-B Champion)

| Metric | Phase 9C-B Eval Baseline |
|--------|-------------------------|
| Mean champion score | ~0.903 (3 eval runs) |
| Approval rate | TBD (after labels) |
| Novelty confidence | TBD (after labels) |
| Technical plausibility | TBD (after labels) |

**Use Phase 9C-B operational baseline as the anchor** for A/B deltas.

---

## Artifact Directories

| Item | Path |
|------|------|
| Phase 9C-B operational baseline | `runtime/baselines/phase9c_operational_baseline_regime2.json` |
| evidence_diversity_v1 policy | `config/policies/evidence_diversity_v1.json` |
| Phase 9D trial artifacts | `runtime/challenger_trials/phase9c_ab_trial/` (to be created) |
| Review labels (Phase 9D) | `runtime/challenger_trials/phase9c_ab_trial/review_labels.csv` |

---

## Key Constraints for Phase 9D

1. **Same embedding regime** for both arms: `BT_EMBEDDING_MODEL=qwen3-embedding:4b`
2. **Same evaluation profile** for both arms: `eval_clean_energy_30m`
3. **No mixing** of Regime 1 (nomic-embed-text) data in the comparison
4. **Label all 12 champions** + at least 12 runner-ups
5. **Manual promotion only** — automatic promotion is OFF
6. **Rollback trigger**: if challenger approval < 50% at any point, stop and diagnose

---

## What evidence_diversity_v1 Changes

| Parameter | Champion Default | evidence_diversity_v1 |
|-----------|-----------------|----------------------|
| api_relevance weight | 0.35 | 0.20 (-43%) |
| mechanism_overlap weight | 0.20 | 0.35 (+75%) |
| All other surfaces | defaults | unchanged |

**Hypothesis**: Mechanism-aligned evidence surfacing provides better mechanistic grounding
without novelty suppression, improving reviewer plausibility assessments.

**Does NOT change**: generation_prompt_variant (standard), scoring_weights (null = defaults),
diversity_steering_variant (standard).

---

## How to Verify Challenger Registration Before Running

```bash
python -m breakthrough_engine policy list
# Should show:
#   Champion: phase5_champion
#   Challengers (1): evidence_diversity_v1

python -m breakthrough_engine ds run eval_clean_energy_30m --policy evidence_diversity_v1 --dry-run
# Should show: "Policy override: evidence_diversity_v1"
```

---

## Review Label Collection After A/B Batch

```bash
python -m breakthrough_engine review list --unlabeled
python -m breakthrough_engine review summary
```

Label schema:
```
approve | defer | reject
novelty_confidence (0.0–1.0)
technical_plausibility (0.0–1.0)
commercialization_relevance (0.0–1.0)
key_flaw (string)
reviewer_note (string)
```

---

## Promotion Decision Protocol

After 6+6 campaigns and 24+ labels:

1. Compute deltas: challenger metrics - champion metrics
2. Check all 4 gates
3. If all pass: PROMOTION_RECOMMENDED → champion promotion decision
4. If any fail: PROMOTION_NOT_RECOMMENDED → retire challenger, design next
5. Document as trusted result (positive or negative)

---

## Relationship to Prior Trials

| Trial | Challenger | Verdict | Key Finding |
|-------|-----------|---------|-------------|
| phase9b_ab_trial | synthesis_focus_v1 | PROMOTION_NOT_RECOMMENDED | Scoring weights are selection tools, not quality levers |
| phase9c_ab_trial | evidence_diversity_v1 | PENDING | Evidence quality intervention hypothesis |

---

## Default Behavior: Stop After Phase 9C-B

Phase 9D should NOT launch until:
1. All 6 Phase 9C-B production campaigns complete with integrity_ok
2. Phase 9C-B review labels are complete (12 minimum)
3. Phase 9C-B operational baseline is frozen and documented
4. No ambiguity about champion baseline metrics
