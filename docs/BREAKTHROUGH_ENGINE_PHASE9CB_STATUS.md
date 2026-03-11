# Phase 9C-B Status

**Phase**: 9C-B — Champion-Only Daily Collection, Regime 2 Operational Baseline
**Branch**: `breakthrough-engine-phase9c-challenger-iteration`
**Base commit**: `109b6da` (Phase 9C complete)
**Date**: 2026-03-11

---

## Summary

| Item | Status |
|------|--------|
| Runtime health check | COMPLETE — all models reachable |
| evidence_diversity_v1 DB registration | COMPLETE |
| synthesis_focus_v1 retired | COMPLETE (is_rolled_back=1 in DB) |
| Blocker fixes applied | COMPLETE (3 CLI bugs fixed) |
| eval daily collection (3 Regime 2 runs) | COMPLETE |
| production daily collection (3 runs) | COMPLETE |
| Review labels | COMPLETE (12/12) |
| Regime 2 operational baseline | COMPLETE (baseline_ready=true) |
| Phase 9D readiness package | COMPLETE |
| Tests | 836 passing, 0 failures |

---

## Health / Readiness Check

| Component | Status |
|-----------|--------|
| Ollama server | REACHABLE (localhost:11434) |
| qwen3.5:9b-q4_K_M | LOADED (6.6 GB, Q4_K_M) |
| qwen3-embedding:4b | LOADED (2.5 GB, Q4_K_M) |
| nomic-embed-text | LOADED (legacy, not used in Regime 2) |
| Champion policy | phase5_champion |
| Challenger (active) | evidence_diversity_v1 (id=3f24a0a2a8074759) |
| Challenger (retired) | synthesis_focus_v1 (id=ba0cb255c20f4995, is_rolled_back=1) |
| eval_clean_energy_30m dry-run | PASS |
| overnight_clean_energy dry-run | PASS |

---

## Blocker Fixes

### Fix 1: policy register missing evidence_ranking_weights

**Symptom**: `policy register --config-path evidence_diversity_v1.json` registered the policy
but did not persist `evidence_ranking_weights` to the DB. The challenger's key surface change
was lost.

**Root cause**: `cli.py` policy register block loaded scoring_weights, generation_prompt_variant,
etc. from the config file but omitted evidence_ranking_weights.

**Fix**: `breakthrough_engine/cli.py` — added evidence_ranking_weights load and pass-through.

**Verification**: `SELECT config_json FROM bt_policies WHERE name='evidence_diversity_v1'`
confirms `evidence_ranking_weights: {api_relevance: 0.20, ..., mechanism_overlap: 0.35, ...}` stored.

### Fix 2: daily run calling CampaignManager.run() (non-existent method)

**Symptom**: All `daily run` commands aborted with
`ERROR: 'CampaignManager' object has no attribute 'run'`.

**Root cause**: `cli.py` daily run handler called `mgr.run(profile_name=...)` but the method
is `run_campaign(profile: CampaignProfile)`. Likely introduced during a refactor without
updating the daily automation call site.

**Fix**: `breakthrough_engine/cli.py` — daily run handler now calls:
1. `load_campaign_profile(profile.campaign_profile)` → `CampaignProfile` object
2. `mgr.run_campaign(campaign_profile_obj, strict_preflight=...)` → `CampaignReceipt`
3. `has_draft = receipt.status == CampaignStatus.COMPLETED_WITH_DRAFT.value`
4. Builds `campaign_result` dict from receipt for downstream review queue consumers

### Fix 3: daily run missing --force flag

**Symptom**: Cannot collect more than 1 campaign per profile per day in a single session
(max-runs-per-day guard blocks subsequent runs).

**Context**: Legitimate for standard daily automation. For batch collection of 3 runs/profile
in one session, a bypass flag is needed.

**Fix**: `breakthrough_engine/cli.py` — added `--force` flag to `daily run` that skips
the `has_daily_run_today` guard. Standard runs (without `--force`) continue to enforce the
daily limit.

---

## Evaluation Daily Collection (3 Valid Runs)

All evaluation campaigns used `OllamaEmbeddingProvider(qwen3-embedding:4b)` = Regime 2.

| Run | Campaign ID | Champion Title | Score | Candidates | Shortlisted |
|-----|-------------|----------------|-------|-----------|-------------|
| eval-1 | 70b85ab1720a4859 | MOF-808 Insulation with Low-Temp Regeneration for Passive Building Cooling | 0.872 | 8 | 3 |
| eval-2 | efe33bd47e524534 | Quantum Dot BiVO4 Photocatalytic Desalination for Offshore Platforms | 0.921 | 8 | 3 |
| eval-3 | 4c5a48429f8c4469 | Quantum Dot-BiVO4 Sensitized Microalgae for Synergistic Bio-hydrogen | 0.917 | 15 | 6 |

**Discarded** (invalid for Regime 2 baseline):
- 6493c0211a144089: MockEmbeddingProvider (BT_EMBEDDING_MODEL not set), excluded

### Evaluation Champion Score Summary (Regime 2)
- Mean: 0.903
- Min: 0.872
- Max: 0.921
- All champions: `APPROVE` (score ≥ 0.75, falsification risk = medium)

---

## Production Daily Collection (Complete)

All three production campaigns completed sequentially using
`BT_EMBEDDING_MODEL=qwen3-embedding:4b`.

| Run | Campaign ID | Champion Title | Score | Candidates | Shortlisted |
|-----|-------------|----------------|-------|-----------|-------------|
| prod-1 | 983beee35a024e0d | Perovskite Tandem Trap Passivation via OABr Analogues | 0.8972 | 31 | 5 |
| prod-2 | a219f3a3f64b4e9a | Quantum dot-sensitized photo-electrochemical hydrogen generation in seawater | 0.8930 | 29 | 5 |
| prod-3 | 3886d50a5b3a4303 | Perovskite Solar Cell Tandem Stacking Increases Charge Collection Efficiency in Concentrated PV-Thermal Systems | 0.9305 | 29 | 5 |

**Production mean champion score**: 0.907
**Batch timing**: 17:15:10 → 20:22:55 (3h 7m 45s total for 3 runs)

---

## Runner-Up Candidate Summary (Evaluation Runs)

| Campaign | Candidate ID | Title | Score | Role |
|---------|-------------|-------|-------|------|
| 70b85ab1 | f2c339531f2f4878 | MOF-808 Insulation with Low-Temp Regeneration | 0.872 | champion |
| 70b85ab1 | 488a0577f2754a1f | Hybrid Heat Pump with High-Efficiency Sulfide Battery Thermal | 0.819 | runner-up |
| 70b85ab1 | 9822df8dc4723fc8 | NiFe-LDH Catalytic Ventilation Filters | 0.831 | runner-up |
| efe33bd4 | a2323ff3d078472a | Quantum Dot BiVO4 Photocatalytic Desalination | 0.921 | champion |
| efe33bd4 | 1a0e29ed9582cdc5 | MOF-808 Offshore Direct Air Capture | 0.911 | runner-up |
| efe33bd4 | 0f5f090add715b2a | Perovskite-Silicon Tandem Modules for Offshore Platforms | 0.921 | runner-up |
| 4c5a4842 | 2a6727f6a43b4ee0 | Quantum Dot-BiVO4 Sensitized Microalgae | 0.917 | champion |
| 4c5a4842 | 87c9de132c2ffb16 | Passivated Perovskite Bio-Photocatalysts | 0.915 | runner-up |
| 4c5a4842 | dd8fd2f3ece09a93 | Flexible Organic Photovoltaics for Bio-Sensing | 0.915 | runner-up |

---

## Phase 9C-B Completion

All deliverables complete. Phase 9C-B is DONE.

- Regime 2 baseline frozen: `runtime/baselines/phase9c_operational_baseline_regime2.json`
- 12 review labels collected: `runtime/phase9c/daily_collection/review_labels.csv`
- Phase 9D readiness package: `docs/BREAKTHROUGH_ENGINE_PHASE9D_READY.md`
- Next: Run Phase 9D evidence_diversity_v1 A/B trial (6+6 campaigns, eval_clean_energy_30m)
