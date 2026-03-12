# Phase 9E Plan: Promotion, Burn-In, Baseline Freeze, Rollback Guardrails

**Phase**: 9E
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Base commit**: `ec715e4` (Phase 9D: evidence_diversity_v1 A/B trial complete — PROMOTION_RECOMMENDED)
**Date created**: 2026-03-12
**Status**: COMPLETE

---

## Objective

Turn the first successful challenger win (evidence_diversity_v1) into a stable production upgrade by:

1. Promoting evidence_diversity_v1 manually and explicitly
2. Running a 6-run burn-in under the promoted policy
3. Freezing the promoted policy as the new Regime 2 production baseline
4. Establishing rollback guardrails
5. Preparing the next challenger iteration without activating it

---

## Current State at Phase 9E Start

| Item | Value |
|------|-------|
| Branch | `breakthrough-engine-phase9c-challenger-iteration` |
| Commit | `ec715e4` |
| Tests | 864 passing, 0 failures |
| Champion (before promotion) | `phase5_champion` |
| Challenger to promote | `evidence_diversity_v1` |
| Trial result | PROMOTION_RECOMMENDED (6+6 A/B, all 4 gates pass) |
| Embedding regime | Regime 2 (qwen3-embedding:4b, 2560d) |
| DB | runtime/bt_engine.db (gitignored) |

---

## Priority Order

### Priority 1 — Manual Promotion
- Execute `policy manual-promote evidence_diversity_v1`
- Confirm `policy list` shows evidence_diversity_v1 as champion
- Export promotion receipt

### Priority 2 — Burn-In Collection
- Run 3 evaluation_daily_clean_energy campaigns
- Run 3 production_daily_clean_energy campaigns
- Collect review labels (champion + 1 runner-up per campaign)
- Validate completeness

### Priority 3 — Baseline Freeze + Rollback
- Produce burn-in comparison summary vs phase9c_operational_baseline_regime2
- Freeze phase9e_promoted_production_baseline_regime2.json
- Document rollback triggers and confirm rollback command works

### Priority 4 — Next-Challenger Prep + Docs
- Design next challenger surface (diversity_steering_variant or negative_memory_strategy)
- Write Phase 10 prep doc
- Create test_phase9e.py

---

## Constraints

- Do not merge to main
- Embedding regime fixed at Regime 2 (qwen3-embedding:4b)
- No automatic promotion for future challengers
- No new active challenger during burn-in
- Keep all tests offline-safe
- Preserve one-publication-per-run invariant

---

## Deliverables Checklist

| Deliverable | Status |
|-------------|--------|
| A: Manual promotion executed | COMPLETE |
| B: Production automation confirmed (champion-only) | COMPLETE |
| C: 6-run burn-in collected | COMPLETE |
| D: Review labels collected | COMPLETE (12/12) |
| E: Burn-in performance summary | COMPLETE |
| F: Regime 2 production baseline frozen | COMPLETE |
| G: Rollback guardrails documented and verified | COMPLETE |
| H: Next-challenger prep completed | COMPLETE |
| I: Artifact manifest updated | COMPLETE |
| J: Tests passing | COMPLETE |
| K: Branch/commit clean | COMPLETE |

---

## Key Artifacts

| Artifact | Path |
|----------|------|
| Promotion receipt | `runtime/phase9e/promotion_receipt.json` |
| Burn-in campaign artifacts | `runtime/phase9e/burnin/campaigns/` |
| Burn-in summary | `runtime/phase9e/burnin/burnin_summary.json` |
| Review labels | `runtime/phase9e/burnin/review_labels.csv` |
| Champions CSV | `runtime/phase9e/burnin/champions.csv` |
| Campaign metrics | `runtime/phase9e/burnin/campaign_metrics.csv` |
| Finalists combined | `runtime/phase9e/burnin/finalists_combined.csv` |
| Label completion | `runtime/phase9e/burnin/label_completion_summary.json` |
| Frozen baseline | `runtime/baselines/phase9e_promoted_production_baseline_regime2.json` |
| Rollback guardrails | `docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md` |
| Phase 10 prep | `docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md` |
