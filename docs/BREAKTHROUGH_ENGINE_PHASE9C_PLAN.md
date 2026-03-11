# Phase 9C Plan: Champion Lock, Challenger Iteration, Daily Collection

**Phase**: 9C
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Base commit**: `ae1908b` (Phase 9B: 6+6 Regime 2 A/B trial complete, PROMOTION_NOT_RECOMMENDED)
**Date**: 2026-03-11

---

## Context

Phase 9B completed the first real Regime 2 6+6 A/B trial. Result: PROMOTION_NOT_RECOMMENDED. The challenger `synthesis_focus_v1` was strictly dominated by the champion on all measured dimensions. Phase 9C locks the current champion into production, documents the failure as a learning artifact, designs one new challenger, and collects reviewed daily data.

---

## Goals

1. **Freeze** the Phase 9B failed challenger as a trusted negative result
2. **Lock** the current champion into production with explicit documentation
3. **Collect** a small reviewed daily dataset under the champion
4. **Design** and register exactly one new challenger (evidence_diversity_v1)
5. **Prove** the new challenger actually actuates runtime behavior
6. **Prepare** for the next A/B batch without running it yet

---

## Constraints

- Do not merge to main
- Do not redesign the architecture
- Keep automatic promotion OFF
- Exactly one active challenger at a time
- Production automation champion-only
- Do not weaken novelty thresholds
- All tests offline-safe
- Do not run a full new A/B batch in this phase

---

## Deliverables

### A: Failed Challenger Freeze

- [x] Freeze `arm_summary.json` with real trial data
- [x] Document failure analysis in `BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md`
- [x] Phase 9B artifacts immutable

### B: Champion Production Lock

- [x] Champion remains: `phase5_champion`
- [x] Daily automation profiles use only champion (no `--policy` flag)
- [x] Explicit documentation of production commands
- [x] No challenger can enter production without manual promotion

### C: Bounded Daily Reviewed Collection

- [ ] Run 3 evaluation_daily_clean_energy + 3 production_daily_clean_energy (requires Ollama)
- [ ] Collect 2 review labels per campaign (champion + runner-up)
- [ ] Export daily_collection_summary.json, daily_collection_summary.md, review_labels.csv, champions.csv, campaign_metrics.csv
- [x] Collection protocol and scaffold documented

### D: Challenger Failure Analysis

- [x] Structured diagnosis in `BREAKTHROUGH_ENGINE_CHALLENGER_FAILURE_ANALYSIS.md`
- [x] Root cause identified: scoring weights are selection tools, not quality levers
- [x] Recurring flaw patterns from reviewer labels documented

### E: Challenger V2 Design

- [x] Register `evidence_diversity_v1` in `config/policies/evidence_diversity_v1.json`
- [x] Design justified in `BREAKTHROUGH_ENGINE_CHALLENGER_V2_DESIGN.md`
- [x] Single surface change: `evidence_ranking_weights`
- [x] synthesis_focus_v1 retired

### F: Proof of Actuation

- [x] Proof artifact in `runtime/phase9c/proof_of_actuation/`
- [x] Shows different evidence ranking between champion and challenger
- [x] Verified via deterministic test (offline-safe)

### G: Review Label Accumulation Support

- [x] Label completeness summary exported
- [x] Workflow for labeling new daily runs documented

### H: Testing

- [ ] `tests/test_breakthrough/test_phase9c.py` — all Phase 9C tests
- [ ] All existing tests preserved
- [ ] Full suite passing

---

## Execution Sequence

```
Phase 9C implementation (no Ollama needed):
  1. Create branch (done)
  2. Freeze Phase 9B artifacts
  3. Create all docs
  4. Register evidence_diversity_v1 policy
  5. Create proof-of-actuation artifact
  6. Create daily collection scaffold
  7. Write tests
  8. Run full suite
  9. Commit

Phase 9C batch (requires Ollama):
  NOTE: daily collection runs must be performed manually when Ollama is available.
  Commands:
    python -m breakthrough_engine daily run evaluation_daily_clean_energy  (3x)
    python -m breakthrough_engine daily run production_daily_clean_energy   (3x)
  Then: collect review labels and update runtime/phase9c/daily_collection/
```

---

## Production Lock Commands

```bash
# Champion-only daily run (evaluation)
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Champion-only daily run (production)
python -m breakthrough_engine daily run production_daily_clean_energy

# Dry-run to verify champion policy
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy

# Inspect current policy state
python -m breakthrough_engine policy list

# Verify champion
python -m breakthrough_engine policy show phase5_champion
```

---

## A/B Batch Commands (for future Phase 9D)

```bash
# Champion arm (standard)
python -m breakthrough_engine ds run eval_clean_energy_30m

# Challenger arm (evidence_diversity_v1)
python -m breakthrough_engine ds run eval_clean_energy_30m --policy evidence_diversity_v1

# Collect labels
python -m breakthrough_engine review list --unlabeled
```
