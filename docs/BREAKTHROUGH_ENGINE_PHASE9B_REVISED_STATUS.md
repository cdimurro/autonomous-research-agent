# Phase 9B-Revised Status

**Branch**: `breakthrough-engine-phase9-policy-actuation`
**Commit**: `bbd7692`
**Date**: 2026-03-10
**Current Step**: Embedding regime boundary documented; baseline scaffold frozen; awaiting batch execution

---

## Git State

| Field | Value |
|-------|-------|
| Branch | `breakthrough-engine-phase9-policy-actuation` |
| Commit | `bbd7692` |
| Base commit | `1b52a0f` (Phase 8B) |
| Working tree | Clean |
| Tests | 779 passing, 0 failures |

---

## System State

| Field | Value |
|-------|-------|
| Champion policy | `phase5_champion` |
| Challenger policy | `synthesis_focus_v1` |
| Auto-promotion | OFF |
| Daily automation mode | Champion-only |
| Schema version | v003 |
| Generation model | `qwen3.5:9b-q4_K_M` (Ollama) |
| Embedding model (active) | `qwen3-embedding:4b` (Regime 2) |
| Old embedding model | `nomic-embed-text` (Regime 1, decommissioned) |
| Regime boundary commit | `bbd7692` |

---

## Deliverable Status

### Deliverable A: Embedding Regime Boundary Documentation ✅
- **File**: `docs/BREAKTHROUGH_ENGINE_EMBEDDING_REGIME_BOUNDARY.md`
- Regime 1 (nomic-embed-text) and Regime 2 (qwen3-embedding:4b) explicitly defined
- Exact boundary commit recorded (`bbd7692`)
- Old baselines marked as NOT directly policy-comparable to new regime
- Regime-aware baseline registry complete

### Deliverable B: New Embedding-Regime Reviewed Baseline Freeze ⏳ PENDING BATCH
- **Scaffold**: `runtime/baselines/phase9_new_embedding_reviewed.json`
- Status: `pending_batch_execution`
- Requires: 5+ champion campaigns under Regime 2
- See Phase 9B Plan for exact commands

### Deliverable C: 6+6 Reviewed A/B Trial Under New Regime ⏳ PENDING BATCH
- **Directory**: `runtime/challenger_trials/phase9b_ab_trial/`
- Status: Scaffold created with placeholder artifacts
- Champion arm: 0/6 campaigns complete
- Challenger arm: 0/6 campaigns complete
- Requires: Production LLM (Ollama available)
- See Phase 9B Plan for exact commands

### Deliverable D: Review Label Collection ⏳ PENDING TRIAL
- **Files**: `runtime/challenger_trials/phase9b_ab_trial/review_labels.csv`
- Status: Pending trial completion
- Required: 24+ labels (champion + runner-up per campaign × 12 campaigns)

### Deliverable E: Review-Weighted Posterior Update ⏳ PENDING LABELS
- **Files**: `runtime/challenger_trials/phase9b_ab_trial/posterior_summary.json/md`
- Status: Pending label collection

### Deliverable F: Manual Promotion Decision ⏳ PENDING POSTERIORS
- **File**: `docs/BREAKTHROUGH_ENGINE_PHASE9B_REVISED_PROMOTION_DECISION.md`
- Current verdict: `INSUFFICIENT_EVIDENCE` (no Regime 2 batch data)
- Blocking requirements: Deliverables B, C, D, E must complete first

### Deliverable G: Champion-Only Daily Automation ✅
- Production daily automation runs champion-only
- Challenger excluded from production
- Commands documented in plan
- No changes required

### Deliverable H: Testing ✅
- 779 passing, 0 failures (no code changes in Phase 9B documentation pass)
- All tests offline-safe

### Deliverable I: Branch / Commit Strategy ✅
- Staying on `breakthrough-engine-phase9-policy-actuation`
- Not merging to main
- Documentation and scaffolds committed cleanly

---

## Phase 8B Trial — Regime Retroactive Classification

The Phase 8B trial (`runtime/challenger_trials/phase8b_trial_20260310/`) was run under Regime 1 (nomic-embed-text). It is now classified as a **Regime 1 trial** and is **not used** for the Phase 9B promotion decision.

| Field | Phase 8B Trial | Notes |
|-------|----------------|-------|
| Trial ID | `phase8b_trial_20260310` | Old regime |
| Embedding model | Regime 1 (`nomic-embed-text`) | Policy actuation was also incomplete |
| Promotion assessment | `insufficient_evidence` | For two reasons: too few campaigns AND inert policy |
| Use in Phase 9B | NOT USED | Different regime, different actuation state |

---

## What the Operator Needs to Do Next

1. **Verify Ollama is available**:
   ```bash
   python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
   ```

2. **Run baseline batch** (5+ champion campaigns, Regime 2):
   ```bash
   for i in 1 2 3 4 5; do
     python -m breakthrough_engine ds run eval_clean_energy_30m
   done
   ```

3. **Freeze new-regime baseline**:
   ```bash
   python -m breakthrough_engine baseline freeze \
     --name phase9_new_embedding_reviewed \
     --batch-id phase9b_baseline_batch
   ```
   Then manually update `runtime/baselines/phase9_new_embedding_reviewed.json` with actual metrics.

4. **Run 6+6 A/B batch**:
   ```bash
   # Champion arm
   for i in 1 2 3 4 5 6; do
     python -m breakthrough_engine ds run eval_clean_energy_30m
   done
   # Challenger arm
   for i in 1 2 3 4 5 6; do
     python -m breakthrough_engine ds run eval_clean_energy_30m --policy synthesis_focus_v1
   done
   ```

5. **Record campaign IDs** from each run output. Then:
   ```bash
   python -m breakthrough_engine challenger-trial build \
     --champion-campaigns <c1,c2,c3,c4,c5,c6> \
     --challenger-id synthesis_focus_v1
   ```

6. **Add review labels** for each campaign (champion + runner-up):
   ```bash
   python -m breakthrough_engine review-label add \
     --campaign-id <id> --candidate-id <id> --decision approve \
     --novelty-confidence 0.8 --technical-plausibility 0.9 \
     --commercialization-relevance 0.7 --reviewer-note "..."
   ```

7. **Run comparison** and export trial:
   ```bash
   python -m breakthrough_engine challenger-trial compare --trial-id phase9b_ab_trial
   python -m breakthrough_engine challenger-trial export --trial-id phase9b_ab_trial
   ```

8. **Update promotion decision doc** based on results.

---

## Blocking Issues

None. Infrastructure is ready. All deliverables pending batch execution are blocked only on Ollama availability.

---

## Last Updated

2026-03-10 — Phase 9B documentation pass complete. Awaiting batch execution.
