# Phase 9C-B Plan: Champion-Only Daily Collection, Regime 2 Operational Baseline

**Phase**: 9C-B
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Base commit**: `109b6da` (Phase 9C complete)
**Date**: 2026-03-11

---

## Context

Phase 9C locked the champion, registered challenger v2 (evidence_diversity_v1), and proved actuation.
Phase 9C-B executes the actual champion-only daily collection batch to establish the Regime 2 operational
baseline, then prepares the system for the evidence_diversity_v1 A/B trial (Phase 9D).

---

## Goals

1. **Verify** runtime health under the current embedding regime (qwen3-embedding:4b)
2. **Run** 3 evaluation_daily_clean_energy + 3 production_daily_clean_energy (champion-only)
3. **Collect** review labels for all 6 champions and at least 1 runner-up per run
4. **Freeze** the 6-run dataset as the Regime 2 operational baseline
5. **Package** all artifacts for analysis and handoff
6. **Prepare** the Phase 9D readiness package for evidence_diversity_v1 A/B trial

---

## Constraints

- Do NOT merge to main
- Do NOT run the challenger A/B batch in this phase
- Keep production champion-only
- All campaigns must use Regime 2 (qwen3-embedding:4b)
- One-publication-per-run invariant preserved
- All tests offline-safe

---

## Code Fixes Required (Blockers)

Two bugs were found and fixed in the daily automation path:

### Fix 1: `policy register --config-path` missing `evidence_ranking_weights`

**File**: `breakthrough_engine/cli.py`
**Problem**: The `policy register` CLI command loaded from JSON but did not extract
`evidence_ranking_weights` from the config file. This meant evidence_diversity_v1 could
not be registered with its key surface change preserved.
**Fix**: Added `evidence_ranking_weights = file_config.get("evidence_ranking_weights")`
to the config file load block and passed it through to `PolicyConfig(...)`.

### Fix 2: `daily run` using `CampaignManager.run()` which does not exist

**File**: `breakthrough_engine/cli.py`
**Problem**: The daily run handler called `mgr.run(profile_name=...)` but
`CampaignManager` only has `run_campaign(profile: CampaignProfile)`. This caused
all `daily run` commands to abort at runtime.
**Fix**:
  - Import `load_campaign_profile` to convert profile name → `CampaignProfile` object
  - Call `mgr.run_campaign(campaign_profile_obj, strict_preflight=...)`
  - Check `receipt.status == CampaignStatus.COMPLETED_WITH_DRAFT.value` (not the absent `draft_id`)
  - Build `campaign_result` dict from receipt fields for downstream consumers

### Fix 3: `daily run` missing `--force` flag

**File**: `breakthrough_engine/cli.py`
**Problem**: The max-runs-per-day guard prevents collecting 3 runs per profile in a single
session (needed for batch collection).
**Fix**: Added `--force` flag to `daily run` that skips the day guard.

---

## Deliverables

### A: Health / Readiness Check

- [x] Ollama reachable — 3 models loaded:
  - `qwen3.5:9b-q4_K_M` (generation, 9.7B Q4_K_M, 6.6 GB)
  - `qwen3-embedding:4b` (embeddings, 4.0B Q4_K_M, 2.5 GB)
  - `nomic-embed-text` (legacy, not used in Regime 2)
- [x] Dry-run passes for evaluation_daily_clean_energy
- [x] Dry-run passes for production_daily_clean_energy
- [x] Champion policy: `phase5_champion` (locked, no challengers in production)
- [x] evidence_diversity_v1 registered in DB (id=3f24a0a2a8074759)
- [x] synthesis_focus_v1 marked rolled_back in DB

### B: 3 Evaluation + 3 Production Champion-Only Runs

- [x] eval #1 (70b85ab1720a4859): completed_with_draft, OllamaEmbeddingProvider
- [x] eval #2 (efe33bd47e524534): completed_with_draft, OllamaEmbeddingProvider
- [x] eval #3 (4c5a48429f8c4469): completed_with_draft, OllamaEmbeddingProvider
- [ ] prod #1: pending
- [ ] prod #2: pending
- [ ] prod #3: pending

Note: A first eval run (6493c0211a144089) used MockEmbeddingProvider due to missing
BT_EMBEDDING_MODEL env var. It is excluded from the Regime 2 baseline.

### C: Review Label Collection

- [ ] 6 champion labels (one per valid campaign)
- [ ] ≥1 runner-up label per campaign (6 total)
- [ ] review_labels.csv updated
- [ ] label_completion_summary.json updated

### D: Regime 2 Operational Baseline Freeze

- [ ] Freeze completed 6-run champion-only dataset
- [ ] Export phase9c_operational_baseline_regime2.json to runtime/baselines/

### E: Batch Summary and Artifact Packaging

- [ ] batch_summary.json
- [ ] batch_summary.md
- [ ] champions.csv updated
- [ ] campaign_metrics.csv updated

### F: Phase 9D Readiness Package

- [ ] docs/BREAKTHROUGH_ENGINE_PHASE9D_READY.md created

---

## Launch Commands (Champion-Only Daily)

```bash
# Evaluation (use --force after first run for batch collection)
BT_EMBEDDING_MODEL=qwen3-embedding:4b \
  python -m breakthrough_engine daily run evaluation_daily_clean_energy [--force]

# Production (use --force after first run for batch collection)
BT_EMBEDDING_MODEL=qwen3-embedding:4b \
  python -m breakthrough_engine daily run production_daily_clean_energy [--force]
```

**CRITICAL**: Always set `BT_EMBEDDING_MODEL=qwen3-embedding:4b` to maintain Regime 2 consistency.
Running without this env var uses MockEmbeddingProvider which is invalid for the baseline.

---

## Campaign Profile Mapping

| Daily Profile | Campaign Profile | Notes |
|--------------|-----------------|-------|
| evaluation_daily_clean_energy | eval_clean_energy_30m | exports evaluation pack, inserts review queue |
| production_daily_clean_energy | overnight_clean_energy | inserts review queue, no eval pack |

---

## Execution Log

| Run | Profile | Outcome | Campaign ID | Champion | Score |
|-----|---------|---------|-------------|---------|-------|
| eval-invalid | evaluation_daily_clean_energy | completed_with_draft | 6493c0211a144089 | Platinum-Leaching Suppression | 0.921 |
| eval-1 | evaluation_daily_clean_energy | completed_with_draft | 70b85ab1720a4859 | MOF-808 Insulation | 0.872 |
| eval-2 | evaluation_daily_clean_energy | completed_with_draft | efe33bd47e524534 | Quantum Dot BiVO4 Desalination | 0.921 |
| eval-3 | evaluation_daily_clean_energy | completed_with_draft | 4c5a48429f8c4469 | Quantum Dot-BiVO4 Microalgae | 0.917 |
| prod-1 | production_daily_clean_energy | TBD | TBD | TBD | TBD |
| prod-2 | production_daily_clean_energy | TBD | TBD | TBD | TBD |
| prod-3 | production_daily_clean_energy | TBD | TBD | TBD | TBD |

---

## Artifact Directories

| Artifact | Location |
|----------|----------|
| Daily collection data | `runtime/phase9c/daily_collection/` |
| Batch summary | `runtime/phase9c/daily_collection/batch_summary.json` |
| Baselines | `runtime/baselines/` |
| Phase 9D plan | `docs/BREAKTHROUGH_ENGINE_PHASE9D_READY.md` |
