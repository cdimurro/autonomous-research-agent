# Phase 9C Daily Collection Protocol

**Phase**: 9C
**Status**: SCAFFOLD READY — batch pending Ollama availability
**Collection directory**: `runtime/phase9c/daily_collection/`

---

## Purpose

Collect a small reviewed production/evaluation dataset under the current champion (`phase5_champion`) in Regime 2 (qwen3-embedding:4b). This establishes:

1. A fresh Regime 2 baseline for the champion under normal daily operation
2. A reviewed label pool for ongoing learning
3. Evidence that daily automation is exercised correctly

---

## Collection Target

| Runs | Profile | Policy |
|------|---------|--------|
| 3 | `evaluation_daily_clean_energy` | champion only (no `--policy` flag) |
| 3 | `production_daily_clean_energy` | champion only (no `--policy` flag) |
| Total | 6 campaigns | — |

**Review labels per campaign**: 2 (champion + runner-up)
**Total labels target**: 12

---

## Commands

```bash
# Evaluation runs (3 total)
python -m breakthrough_engine daily run evaluation_daily_clean_energy
python -m breakthrough_engine daily run evaluation_daily_clean_energy
python -m breakthrough_engine daily run evaluation_daily_clean_energy

# Production runs (3 total)
python -m breakthrough_engine daily run production_daily_clean_energy
python -m breakthrough_engine daily run production_daily_clean_energy
python -m breakthrough_engine daily run production_daily_clean_energy

# Inspect unlabeled items after each run
python -m breakthrough_engine review list --unlabeled
```

---

## Per-Run Capture Template

For each run, record in `campaign_metrics.csv`:

| Field | Description |
|-------|-------------|
| campaign_id | Campaign UUID |
| profile | evaluation_daily_clean_energy or production_daily_clean_energy |
| policy | phase5_champion |
| status | COMPLETED or COMPLETED_NO_PUBLICATION |
| champion_title | Title of winning candidate |
| champion_score | Score of winning candidate |
| finalist_count | Number of finalists generated |
| integrity_status | integrity_ok or integrity_fail |
| review_queue_inserted | true/false |
| artifact_path | Path to campaign artifact |

---

## Label Schema (unchanged from Phase 8B)

```
id, campaign_id, candidate_id, candidate_title, candidate_role,
decision, novelty_confidence, technical_plausibility, commercialization_relevance,
key_flaw, reviewer_note, reviewer, created_at
```

**decision values**: approve | defer | reject
**candidate_role values**: champion | runner_up

---

## Export Artifacts

After collection and labeling, produce:

1. `daily_collection_summary.json` — structured summary of all 6 campaigns
2. `daily_collection_summary.md` — human-readable summary
3. `review_labels.csv` — all review labels for the 6 campaigns
4. `champions.csv` — champion candidate details for each campaign
5. `campaign_metrics.csv` — per-campaign metrics

---

## Label Completeness Reporting

After each labeling session:

```bash
# Count unlabeled items
python -m breakthrough_engine review list --unlabeled

# Export label completeness summary
python -m breakthrough_engine review summary
```

The Phase 9C label completeness summary will be at:
`runtime/phase9c/daily_collection/label_completeness_summary.json`

---

## Quality Gates Before New A/B Batch

Before starting Phase 9D A/B batch:

1. All 6 Phase 9C daily campaigns completed with `integrity_ok`
2. All 12 Phase 9C review labels collected
3. Phase 9C champion mean score ≥ 0.88 (Regime 2 baseline confirmation)
4. Phase 9C approval rate ≥ 60%

---

## Relationship to Phase 9B Baseline

The Phase 9B arm_summary recorded champion campaigns under the same profile and regime. Phase 9C daily collection extends this with:
- 6 additional champion campaigns (evaluation + production profiles)
- Labels from a fresh labeling session

Combined Phase 9B + 9C champion data provides a richer baseline for Phase 9D A/B comparison.
