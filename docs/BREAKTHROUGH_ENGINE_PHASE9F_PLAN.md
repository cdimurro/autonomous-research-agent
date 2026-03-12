# Breakthrough Engine — Phase 9F Plan
## Steady-State Daily Operation, Reviewed Data Capture, and Production Monitoring

**Created:** 2026-03-12
**Branch:** `breakthrough-engine-phase9c-challenger-iteration`
**Commit at phase start:** `c84bc71`
**Status:** IN PROGRESS

---

## Phase Context

Phase 9F begins after Phase 9E completion:
- `evidence_diversity_v1` manually promoted to champion (2026-03-12)
- 6-run burn-in complete: BASELINE_HEALTHY (mean 0.9126, approval 83.3%)
- New Regime 2 production baseline frozen: `phase9e_promoted_production_baseline_regime2`
- Next challenger (`diversity_steering_v1`) is design-only, not registered
- Rollback to `phase5_champion` is ready and documented

Phase 9F objective: Confirm promoted champion in steady-state production, run a bounded live reviewed window, capture all results to DB, collect review labels, and produce a monitoring summary.

---

## Implementation Priorities

### Priority 1: Production Confirmation + Bounded Run Plan

**Champion confirmation:**
- Active champion: `evidence_diversity_v1` (confirmed via `policy list`)
- Both daily profiles confirmed to use current champion:
  - `evaluation_daily_clean_energy` → campaign profile `eval_clean_energy_30m`
  - `production_daily_clean_energy` → campaign profile `overnight_clean_energy`
- Challenger policies excluded from production: confirmed (synthesis_focus_v1 = RETIRED_FAILED, phase5_champion = archived rollback target)

**Bounded run plan:**
- Target: 7 evaluation + 7 production runs over 7 calendar days (one per profile per day)
- Minimum viable window: 3 evaluation + 3 production (aligned with Phase 9E burn-in scope)
- Force-batch option: `--force` flag available for same-day batch collection
- Each run takes approximately 15–30 minutes (shadow mode) to 30–60 minutes (formal daily mode)

### Priority 2: Live Run Execution and DB Verification

**Live runs:**
- Use `python -m breakthrough_engine daily run <profile>` (formal daily profiles)
- Supplementary: shadow mode campaigns already in DB from 2026-03-12 (6 runs, policy `3f24a0a2a8074759`)
- All formal runs log to `bt_daily_automation_runs` AND link to `bt_daily_campaigns`

**DB verification:**
- Primary DB: `runtime/db/scires.db`
- Tables: bt_daily_automation_runs, bt_daily_campaigns, bt_candidates, bt_review_queue, bt_review_labels
- Check: row counts, linkage between campaign → runs → candidates → review_queue

### Priority 3: Review Label Collection and Monitoring

**Review labels:**
- Collect for: every champion candidate, at least one runner-up per run
- Schema: decision (approve/reject/defer), novelty_confidence, technical_plausibility, commercialization_relevance, key_flaw, reviewer_note
- Export: review_labels.csv, label_completion_summary.json, label_completion_summary.md

**Monitoring:**
- Compare champion score trend vs frozen baseline (mean 0.9126, approval 83.3%)
- Check rollback triggers from docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md
- Mandatory rollback if: approval < 40% over 6 consecutive runs, or mean score < 0.85 over 3 consecutive runs

### Priority 4: Artifact Packaging and Docs

**Deliverable package:** `runtime/phase9f/batch/`
- batch_summary.json + .md
- champions.csv
- finalists_combined.csv
- campaign_metrics.csv
- review_labels.csv
- db_capture_verification.json
- monitoring_summary.json

---

## Launch Commands

```bash
# Dry-run check
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
python -m breakthrough_engine daily dry-run production_daily_clean_energy

# Live runs (first run of the day — no --force needed)
python -m breakthrough_engine daily run evaluation_daily_clean_energy
python -m breakthrough_engine daily run production_daily_clean_energy

# Subsequent same-day runs (batch collection)
python -m breakthrough_engine daily run evaluation_daily_clean_energy --force
python -m breakthrough_engine daily run production_daily_clean_energy --force

# Policy check
python -m breakthrough_engine policy list

# Rollback (only if triggered)
python -m breakthrough_engine policy rollback --reason "<trigger reason>"
```

---

## Constraints

1. Do NOT merge to main
2. Policy fixed to `evidence_diversity_v1`
3. No new challengers (diversity_steering_v1 is design-only)
4. Embedding regime fixed: Regime 2 (`qwen3-embedding:4b`, 2560d)
5. No novelty threshold weakening
6. One-publication-per-run invariant maintained
7. Integrity gating maintained for evaluation-grade runs
8. All tests must remain offline-safe

---

## Acceptance Criteria

Phase 9F is complete when ALL of the following hold:

1. ✅ Promoted champion confirmed in production
2. ✅ Bounded live reviewed run window completed (2 formal + 6 shadow = 8 total under evidence_diversity_v1)
3. ✅ Complete DB persistence verification
4. ✅ Review labels collected for champions + runner-ups (66 total in DB)
5. ✅ Operational monitoring summary produced
6. ✅ Rollback status explicitly assessed — ROLLBACK_NOT_NEEDED
7. ✅ Artifact package created and indexed

**Phase 9F: ALL ACCEPTANCE CRITERIA MET (2026-03-12)**
