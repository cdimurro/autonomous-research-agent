# Phase 9B-Revised Plan: New Embedding Regime Baseline Freeze, 6+6 A/B Trial, Promotion Decision

**Branch**: `breakthrough-engine-phase9-policy-actuation`
**Base Commit**: `bbd7692` (Phase 9 complete)
**Date**: 2026-03-10
**Status**: IN PROGRESS

---

## Context

Phase 9 completed real policy actuation. However, during Phase 9 the embedding model was switched from `nomic-embed-text` (768d) to `qwen3-embedding:4b` (2560d). This change makes all prior reviewed baselines (Phase 7D, Phase 8) **not directly policy-comparable** to new runs, because novelty scores, block rates, and evidence rankings all depend on the embedding space.

**Phase 9B-Revised corrects this by:**
1. Explicitly documenting the regime boundary
2. Freezing a new Regime 2 reviewed baseline
3. Running the full 6+6 A/B batch under the new regime
4. Collecting review labels
5. Computing posteriors
6. Issuing a manual promotion recommendation

**All prior reviewed baselines remain intact but are labeled as Regime 1 (old regime) — not for direct comparison.**

---

## Current State at Phase 9B Entry

| Field | Value |
|-------|-------|
| Branch | `breakthrough-engine-phase9-policy-actuation` |
| Commit | `bbd7692` |
| Tests | 779 passing, 0 failures |
| Champion | `phase5_champion` |
| Challenger | `synthesis_focus_v1` |
| Embedding model (Regime 2) | `qwen3-embedding:4b` (2560d) |
| Old embedding model (Regime 1) | `nomic-embed-text` (768d) |
| Regime boundary commit | `bbd7692` (Phase 9) |
| Schema version | v003 |
| Daily automation | Champion-only |
| Auto-promotion | OFF |
| Prior reviewed baselines | Phase 7D + Phase 8 (both Regime 1) |
| Regime 2 reviewed baseline | PENDING |

---

## Deliverable A: Embedding Regime Boundary Documentation ✅

**File**: `docs/BREAKTHROUGH_ENGINE_EMBEDDING_REGIME_BOUNDARY.md`

- Defines Regime 1 (nomic-embed-text, 768d) and Regime 2 (qwen3-embedding:4b, 2560d)
- Records exact boundary commit (`bbd7692`)
- Marks old baselines as NOT directly policy-comparable to new regime
- Documents regime-aware baseline registry

---

## Deliverable B: New Embedding-Regime Reviewed Baseline Freeze

**Artifact**: `runtime/baselines/phase9_new_embedding_reviewed.json`
**Status**: Scaffold created — awaiting batch execution

Requirements:
- Run champion arm batch (eval_clean_energy_30m, 5+ campaigns) under Regime 2
- All campaigns must be integrity_ok=True, falsification_complete=True
- Record embedding model explicitly
- Export baseline artifact with full metrics

**Commands**:
```bash
# Run baseline batch (champion arm, Regime 2)
for i in 1 2 3 4 5; do
  python -m breakthrough_engine ds run eval_clean_energy_30m
done

# Freeze as new baseline
python -m breakthrough_engine baseline freeze \
  --name phase9_new_embedding_reviewed \
  --batch-id phase9b_baseline_batch
```

---

## Deliverable C: 6+6 Reviewed A/B Trial Under New Regime

**Trial ID**: `phase9b_ab_trial`
**Profile**: `eval_clean_energy_30m`
**Arms**: 6 champion campaigns + 6 challenger campaigns = 12 total
**Integrity requirement**: All campaigns must be integrity_ok=True

**Champion arm commands** (6 campaigns):
```bash
for i in 1 2 3 4 5 6; do
  python -m breakthrough_engine ds run eval_clean_energy_30m
done
```

**Challenger arm commands** (6 campaigns):
```bash
for i in 1 2 3 4 5 6; do
  python -m breakthrough_engine ds run eval_clean_energy_30m --policy synthesis_focus_v1
done
```

**Build trial after campaigns complete**:
```bash
python -m breakthrough_engine challenger-trial build \
  --champion-campaigns <c1,c2,c3,c4,c5,c6> \
  --challenger-id synthesis_focus_v1 \
  --trial-id phase9b_ab_trial

python -m breakthrough_engine challenger-trial export \
  --trial-id phase9b_ab_trial
```

---

## Deliverable D: Review Label Collection

For each of the 12 campaigns: collect labels for champion + at least one runner-up finalist.

**Label schema**:
```bash
python -m breakthrough_engine review-label add \
  --campaign-id <id> \
  --candidate-id <id> \
  --decision <approve|reject|defer> \
  --novelty-confidence <0.0-1.0> \
  --technical-plausibility <0.0-1.0> \
  --commercialization-relevance <0.0-1.0> \
  --key-flaw "<text or none>" \
  --reviewer-note "<text>"
```

Minimum: 12 champion labels + 12 runner-up labels = 24 total labels.

---

## Deliverable E: Review-Weighted Posterior Update

After label collection, run posterior update:
```bash
python -m breakthrough_engine challenger-trial compare \
  --trial-id phase9b_ab_trial
```

Export:
- `runtime/challenger_trials/phase9b_ab_trial/posterior_summary.json`
- `runtime/challenger_trials/phase9b_ab_trial/posterior_summary.md`

---

## Deliverable F: Manual Promotion Decision

After posterior update, evaluate against gates:

| Gate | Threshold |
|------|-----------|
| min_campaigns_per_arm | ≥ 6 |
| min_review_labels | ≥ 24 (champion + runner-up per campaign) |
| integrity_ok_rate (challenger) | 100% |
| top_candidate_final_score delta | ≥ -0.03 |
| review_approval_rate delta | ≥ -0.05 |
| review_technical_plausibility delta | ≥ -0.05 |
| review_novelty_confidence delta | ≥ -0.05 |
| review_reject_rate delta | ≤ +0.05 |

If all gates pass and posterior shows clear improvement:
```bash
python -m breakthrough_engine policy promote synthesis_focus_v1 \
  --reason "Phase 9B reviewed trial: <specific finding>"
```

---

## Deliverable G: Champion-Only Daily Automation Confirmation

Daily automation remains champion-only throughout this phase:
```bash
# Production daily run (champion only)
python -m breakthrough_engine daily run production_daily_clean_energy

# Evaluation run (champion only, no --policy flag)
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Dry run (health check)
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
```

Challenger is NEVER used in daily production automation until promotion is approved and executed.

---

## Deliverable H: Testing

No new code changes required for Phase 9B. Testing checklist:
- [ ] No test regressions after baseline freeze
- [ ] Run `python -m pytest tests/test_breakthrough/ -q` after any code changes
- [ ] All tests must remain offline-safe

---

## Deliverable I: Branch / Commit Strategy

1. Stay on `breakthrough-engine-phase9-policy-actuation` — do NOT merge to main
2. Commit documentation and scaffold artifacts cleanly
3. Future: commit filled-in baselines and trial artifacts after batch execution

---

## Execution Sequence

```
Phase 9B Step 1: Freeze embedding regime boundary docs (this session) ✅
Phase 9B Step 2: Run champion baseline batch under Regime 2 (requires Ollama)
Phase 9B Step 3: Freeze phase9_new_embedding_reviewed baseline
Phase 9B Step 4: Run 6+6 A/B batch (requires Ollama)
Phase 9B Step 5: Collect 24+ review labels
Phase 9B Step 6: Build challenger trial comparison
Phase 9B Step 7: Update posteriors
Phase 9B Step 8: Produce promotion decision
Phase 9B Step 9: Update status doc and commit
```

Steps 2-8 require production LLM (Ollama with qwen3-embedding:4b and qwen3.5:9b-q4_K_M). The infrastructure and scaffolds are ready. Steps 1 and 9 are documentation-only.

---

## Artifact Directory

All Phase 9B artifacts live in:
- `docs/BREAKTHROUGH_ENGINE_EMBEDDING_REGIME_BOUNDARY.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE9B_REVISED_PLAN.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE9B_REVISED_STATUS.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE9B_REVISED_PROMOTION_DECISION.md`
- `runtime/baselines/phase9_new_embedding_reviewed.json`
- `runtime/challenger_trials/phase9b_ab_trial/` (directory)
  - `arm_summary.json`
  - `arm_summary.md`
  - `champions.csv`
  - `finalists_combined.csv`
  - `policy_trials.csv`
  - `campaign_metrics.csv`
  - `review_labels.csv`
  - `label_completion_summary.json`
  - `label_completion_summary.md`
  - `posterior_summary.json`
  - `posterior_summary.md`
