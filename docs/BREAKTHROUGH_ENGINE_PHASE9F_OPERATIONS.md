# Breakthrough Engine — Phase 9F Operations
## Daily Operation Runbook

**Phase:** 9F
**Created:** 2026-03-12
**Champion:** `evidence_diversity_v1`

---

## System Overview

### Active Production Configuration

| Component | Value |
|-----------|-------|
| Champion policy | `evidence_diversity_v1` |
| Policy surface changed | `evidence_ranking_weights` only |
| evidence_ranking_weights | mechanism_overlap=0.35, api_relevance=0.20, domain_overlap=0.30, baseline=0.15 |
| Generation prompt variant | `standard` (unchanged) |
| Diversity steering variant | `standard` (unchanged) |
| Scoring weights | `null` (champion defaults) |
| Embedding model | `qwen3-embedding:4b` (Regime 2, 2560d) |
| Generation model | `qwen3.5:9b-q4_K_M` via Ollama |
| DB | `runtime/db/scires.db` |
| Branch | `breakthrough-engine-phase9c-challenger-iteration` |

---

## Launch Commands

### Pre-run Checks

```bash
# Confirm champion
python -m breakthrough_engine policy list

# Expected output:
# Champion: evidence_diversity_v1 (id=evidence_diversity_v1) version=1.0

# Dry-run (inspect without executing)
python -m breakthrough_engine daily dry-run evaluation_daily_clean_energy
python -m breakthrough_engine daily dry-run production_daily_clean_energy

# Check today's runs
python -m breakthrough_engine daily status
```

### Daily Evaluation Run

```bash
PYTHONPATH=/Users/openclaw/breakthrough-engine \
  .venv/bin/python -m breakthrough_engine daily run evaluation_daily_clean_energy
```

- Profile: `evaluation_daily_clean_energy`
- Campaign profile: `eval_clean_energy_30m`
- Requires: `integrity_ok=true`, `falsification_complete=true`
- Exports: evaluation pack (schema v003)
- Inserts: review queue item for champion

### Daily Production Run

```bash
PYTHONPATH=/Users/openclaw/breakthrough-engine \
  .venv/bin/python -m breakthrough_engine daily run production_daily_clean_energy
```

- Profile: `production_daily_clean_energy`
- Campaign profile: `overnight_clean_energy`
- Requires: best-effort (not hard-fail)
- Inserts: review queue item if draft produced

### Batch Collection (Force Mode)

```bash
# Skip max-runs-per-day guard — for batch collection windows only
python -m breakthrough_engine daily run evaluation_daily_clean_energy --force
python -m breakthrough_engine daily run production_daily_clean_energy --force
```

---

## Daily Review Workflow

1. Run evaluation_daily_clean_energy (morning)
2. Run production_daily_clean_energy (morning or overnight)
3. Check review queue: `python -m breakthrough_engine review list`
4. Review champion candidate: `python -m breakthrough_engine review show <queue_id>`
5. Label champion: `python -m breakthrough_engine review approve/reject/defer <queue_id>`
6. Label runner-up if available

---

## Monitoring Checks

Run after each batch of 6 runs:

```python
# Quick monitoring query against runtime/db/scires.db
import sqlite3, json
conn = sqlite3.connect('runtime/db/scires.db')
cur = conn.cursor()
cur.execute('''
    SELECT dc.result_json, dc.started_at
    FROM bt_daily_campaigns dc
    WHERE dc.policy_id IN ('evidence_diversity_v1', '3f24a0a2a8074759')
    ORDER BY dc.started_at DESC LIMIT 12
''')
```

### Score Thresholds (from frozen baseline)

| Metric | Frozen Baseline | Warning Threshold | Mandatory Rollback |
|--------|----------------|-------------------|-------------------|
| Mean champion score | 0.9126 | < 0.88 | < 0.85 over 3 runs |
| Approval rate | 83.3% | < 60% | < 40% over 6 runs |
| Novelty confidence | 0.853 | < 0.79 | — |
| Technical plausibility | 0.855 | < 0.80 | — |

---

## Rollback Procedure

### Mandatory Rollback Triggers

1. Approval rate < 40% over 6 consecutive runs
2. Mean score < 0.85 over 3 consecutive runs
3. Integrity failures on 3 consecutive eval runs
4. Reject rate ≥ 3/6 consecutive champion labels

### Rollback Command

```bash
python -m breakthrough_engine policy rollback --reason "<specific trigger reason>"
```

### After Rollback

- Verify: `python -m breakthrough_engine policy list` → Champion should show `phase5_champion`
- Document: Update PHASE9F_STATUS.md with rollback timestamp and reason
- Preserve: All Phase 9F data (do not delete campaigns or labels)

---

## DB Query Reference

```bash
# Count recent runs by policy
sqlite3 runtime/db/scires.db "
  SELECT policy_id, count(*) as n
  FROM bt_daily_campaigns
  WHERE started_at >= '2026-03-12'
  GROUP BY policy_id
"

# Recent review queue items
sqlite3 runtime/db/scires.db "
  SELECT campaign_id, champion_title, champion_score, review_status, inserted_at
  FROM bt_review_queue
  ORDER BY inserted_at DESC LIMIT 10
"

# Label summary
sqlite3 runtime/db/scires.db "
  SELECT decision, count(*) as n
  FROM bt_review_labels
  GROUP BY decision
"
```

---

## File Paths

| Path | Purpose |
|------|---------|
| `runtime/db/scires.db` | Primary database |
| `runtime/phase9e/` | Phase 9E artifacts (burn-in, promotion receipt) |
| `runtime/phase9f/` | Phase 9F artifacts (this phase) |
| `runtime/baselines/phase9e_promoted_production_baseline_regime2.json` | Frozen baseline reference |
| `config/policies/evidence_diversity_v1.json` | Champion policy config |
| `config/daily_profiles/evaluation_daily_clean_energy.yaml` | Eval daily profile |
| `config/daily_profiles/production_daily_clean_energy.yaml` | Production daily profile |
| `docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md` | Rollback triggers |

---

## Embedded Policy Snapshot (Phase 9F)

```json
{
  "id": "evidence_diversity_v1",
  "name": "evidence_diversity_v1",
  "version": "1.0",
  "evidence_ranking_weights": {
    "mechanism_overlap": 0.35,
    "api_relevance": 0.20,
    "domain_overlap": 0.30,
    "baseline": 0.15
  },
  "generation_prompt_variant": "standard",
  "diversity_steering_variant": "standard",
  "scoring_weights": null,
  "embedding_regime": "regime_2"
}
```
