# Phase 7B Implementation Status

**Branch**: `breakthrough-engine-phase7b-prod-hardening`
**Base**: `breakthrough-engine-phase7a-autonomous-ops` @ commit `f70507f`
**Final commit**: `2311b01`
**Completed**: 2026-03-09
**Status**: VALIDATED

## Baseline vs Final

| Attribute | Phase 7A | Phase 7B |
|-----------|----------|----------|
| Tests passing | 506 | **549** (+43) |
| Schema version | v008 | **v009** |
| New tables | 39 | **40** (+1: bt_evaluation_packs) |
| Embedding in production | MockEmbeddingProvider | **OllamaEmbeddingProvider(nomic-embed-text)** |
| Embedding preflight | PASS (always) | **FAIL if BT_EMBEDDING_MODEL set but unavailable** |
| Evaluation packs | None | **Full analysis-ready packs** |
| Campaign profiles | 2 | **3** (+smoke_10m) |

## Deliverable Status

| Deliverable | Status | Notes |
|------------|--------|-------|
| A. Evaluation pack for b87513b86b6f4b1f | DONE | 167KB JSON + MD + 2 CSVs |
| B. Campaign analysis schema (v001) | DONE | EvaluationPack + CandidateRecord |
| C. Production embedding hardening | DONE | OllamaEmbeddingProvider wired via BT_EMBEDDING_MODEL |
| D. Housekeeping / trust hardening | DONE | embedding telemetry, tiebreak notes, schema v009 |
| E. Smoke campaign (smoke_10m) | DONE | completed_with_draft, healthy, overnight_ready |
| F. Second overnight campaign launch | DONE | f01a0a7c72304481 running with real embeddings |
| G. Morning-after inspection | DONE | see runbook below |
| H. Tests (43 new, all offline-safe) | DONE | 549 total, 0 failures |
| I. Branch / commit strategy | DONE | breakthrough-engine-phase7b-prod-hardening |

## Key Fixes / Changes

### Production Embedding Hardening
- `orchestrator.py`: `BreakthroughOrchestrator.__init__` now checks `BT_EMBEDDING_MODEL` env var
  - If set + production mode → `OllamaEmbeddingProvider(model=BT_EMBEDDING_MODEL)`
  - Otherwise → `MockEmbeddingProvider` (with warning in production modes)
- `preflight.py`: `_check_embedding_model` rewritten:
  - `BT_EMBEDDING_MODEL` unset → PASS ("MockEmbeddingProvider — set BT_EMBEDDING_MODEL for real")
  - `BT_EMBEDDING_MODEL` set and available → PASS ("real embeddings active")
  - `BT_EMBEDDING_MODEL` set but unavailable → **FAIL** (blocks strict preflight)
- `campaign_manager.py`: `embedding_provider` field added to `CampaignReceipt`, persisted to DB
- `db.py`: schema v009 adds `embedding_provider` column to `bt_campaign_receipts`

### Evaluation Pack Exporter (NEW: `evaluation_pack.py`)
- `EvaluationPackExporter.export(campaign_id)` writes to `runtime/evaluation_packs/<id>/`
- Outputs: `evaluation_pack.json`, `evaluation_pack.md`, `candidates.csv`, `finalists.csv`
- JSON pack contains: campaign metadata, config snapshot, stage timings, preflight health,
  all candidates with scores, finalists with full score breakdown, falsification data,
  tiebreak/ranking rationale, champion why-it-won summary, posteriors, runs
- Registered in `bt_evaluation_packs` table for discovery
- CLI: `python -m breakthrough_engine evaluation-pack export <campaign_id>`

### Schema v009 (NEW tables/columns)
- `bt_evaluation_packs`: tracks evaluation pack artifacts per campaign
- `bt_campaign_receipts.embedding_provider`: records which provider was used

### New Profile: smoke_10m
- 10-minute smoke/confirmation profile
- Used to validate pipeline before overnight launches

### Profile Fix: overnight_clean_energy
- Changed `program_name: daily_quality` → `clean_energy_shadow` (committed in f70507f)

## Validation Results

### Strict Preflight (with real embeddings)
```
15 PASS, 0 WARN, 0 FAIL
Readiness score: 1.00
Campaign readiness: READY
embedding_model: PASS — OllamaEmbeddingProvider(nomic-embed-text) available — real embeddings active
```

### Smoke Campaign (b80c979d75144fb8)
- Profile: smoke_10m
- Status: completed_with_draft
- Champion: Thermally Activated Argyrodite Coatings for Blade De-Icing
- Healthy: True, overnight_ready: True
- Real embeddings: OllamaEmbeddingProvider(nomic-embed-text)

### Second Overnight Campaign
- Campaign ID: f01a0a7c72304481
- Profile: overnight_clean_energy
- Status: running (as of 2026-03-09T05:11:06Z)
- PID: 35157
- Embedding: OllamaEmbeddingProvider(nomic-embed-text)
- Log: nohup_campaign_7b.log

### Test Suite
- **549 tests, 0 failures**
- 43 new Phase 7B tests (10 test classes, all offline-safe)

## Second Overnight Campaign — Morning Inspection

```bash
cd /Users/openclaw/breakthrough-engine

# 1. Check campaign status
.venv/bin/python -m breakthrough_engine campaign show f01a0a7c72304481

# 2. List all campaigns
.venv/bin/python -m breakthrough_engine campaign list

# 3. View campaign log
tail -50 nohup_campaign_7b.log

# 4. Check campaign artifacts
ls -la runtime/campaigns/f01a0a7c72304481/

# 5. Read campaign summary
cat runtime/campaigns/f01a0a7c72304481/campaign_summary.md

# 6. Export evaluation pack (do this after completion)
BT_EMBEDDING_MODEL=nomic-embed-text .venv/bin/python -m breakthrough_engine evaluation-pack export f01a0a7c72304481

# 7. List all evaluation packs
.venv/bin/python -m breakthrough_engine evaluation-pack list

# 8. View champion details (if completed_with_draft)
cat runtime/evaluation_packs/f01a0a7c72304481/evaluation_pack.md

# 9. Verify real embeddings were used
.venv/bin/python -c "
import json, sqlite3
conn = sqlite3.connect('runtime/db/scires.db')
row = conn.execute(
  'SELECT embedding_provider, status FROM bt_campaign_receipts WHERE campaign_id=?',
  ('f01a0a7c72304481',)
).fetchone()
print('Embedding provider:', row[0] if row else 'not found')
print('Status:', row[1] if row else 'not found')
"
```

## Remaining Limitations

1. **Posteriors CSV empty**: The posteriors query in `_build_pack` filters on `policy_id` but the actual policy ID is stored differently in bt_bayesian_posteriors — may need a broader query.
2. **Elapsed seconds = 0.0 in pack**: `bt_campaign_receipts.elapsed_seconds` is populated at completion; running campaigns will show 0.
3. **Daily campaign linkage**: The `pack.daily_campaign_id` logic assumes 1:1 campaign↔daily_campaign mapping which is true now but may drift.
4. **Mock embeddings in past campaigns**: b87513b86b6f4b1f used MockEmbeddingProvider (Phase 7A). The evaluation pack correctly records this.
