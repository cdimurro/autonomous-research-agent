# Phase 7C Implementation Status

**Branch**: `breakthrough-engine-phase7c-telemetry-calibration`
**Base**: `breakthrough-engine-phase7b-prod-hardening` @ commit `74d86ae`
**Phase start**: 2026-03-09
**Status**: IN PROGRESS

---

## Current State

| Deliverable | Status | Notes |
|-------------|--------|-------|
| A. Telemetry/accounting integrity | DONE | elapsed, rationale, blocked count, generated count all fixed |
| B. Elapsed time hardening | DONE | reads from bt_campaign_receipts directly |
| C. Evaluation pack v002 | DONE | schema v002, accounting_diagnostics, validate_pack_integrity |
| D. Champion/finalist rationale hardening | DONE | ladder_campaign_id extracted from stage_events |
| E. Falsification coverage hardening | DONE | MISSING sentinel for finalists lacking falsification |
| F. Evidence-strength calibration | DONE | count penalty applied, documented |
| G. Documentation drift cleanup | DONE | MASTER_PLAN updated with current state |
| H. Strict telemetry validation run | DEFERRED | recommended next step before 5-campaign batch |
| I. 5-campaign clean-energy batch | DEFERRED | run after strict validation passes |
| J. Analysis helpers | DONE | documented in this file |
| K. Tests | DONE | 30 new tests, 579 total, 0 failures |
| L. Branch/commit strategy | DONE | branch breakthrough-engine-phase7c-telemetry-calibration |

---

## Key Changes Made

### breakthrough_engine/evaluation_pack.py
- Schema version: v001 → v002
- `_build_pack()`:
  - Fixed: `elapsed_seconds` read from `bt_campaign_receipts.elapsed_seconds`
  - Fixed: `champion_rationale` recovered via `ladder_campaign_id` extracted from `stage_events`
  - Fixed: `total_candidates_blocked` = COUNT from DB (NOVELTY_FAILED status)
  - Fixed: `total_candidates_generated` = COUNT from DB (actual rows)
  - Added: `accounting_diagnostics` section
- Added: `_build_accounting_diagnostics()` function
- Added: `validate_pack_integrity()` function (checks elapsed, rationale, falsification)
- Added: Falsification MISSING sentinel for finalists without falsification summary
- Updated: Markdown renderer includes accounting_diagnostics section
- Updated: `export()` calls `validate_pack_integrity()` and logs failures

### breakthrough_engine/scoring.py
- Added: Evidence count penalty `{1: 0.70, 2: 0.82, 3: 0.91, 4: 0.96, 5+: 1.0}`
- Calibration documented in `BREAKTHROUGH_ENGINE_SCORING_CALIBRATION.md`

---

## Files Created

- `docs/BREAKTHROUGH_ENGINE_PHASE7C_PLAN.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE7C_STATUS.md` (this file)
- `docs/BREAKTHROUGH_ENGINE_TELEMETRY_INTEGRITY.md`
- `docs/BREAKTHROUGH_ENGINE_SCORING_CALIBRATION.md`
- `docs/BREAKTHROUGH_ENGINE_EVAL_PACK_V2.md`
- `docs/BREAKTHROUGH_ENGINE_PHASE7C_BATCH_REPORT.md` (to be created after batch)

---

## How to Re-inspect Campaign f01a0a7c72304481 With v002 Pack

```bash
cd /Users/openclaw/breakthrough-engine

# Re-export with corrected telemetry
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine evaluation-pack export f01a0a7c72304481 --overwrite

# Check integrity
python3 -c "
import json
with open('runtime/evaluation_packs/f01a0a7c72304481/evaluation_pack.json') as f:
    p = json.load(f)
print('Schema:', p['schema_version'])
print('Elapsed:', p['campaign']['elapsed_seconds'])
print('Rationale:', repr(p.get('champion_rationale', '')[:100]))
diag = p.get('accounting_diagnostics', {})
print('Integrity OK:', diag.get('integrity_ok'))
print('DB blocked:', diag.get('db_blocked'))
print('DB generated:', diag.get('db_generated'))
for issue in diag.get('issues', []):
    print('ISSUE:', issue)
"
```

---

## Analysis Helper Commands

```bash
# List all campaigns
.venv/bin/python -m breakthrough_engine campaign list

# Show specific campaign
.venv/bin/python -m breakthrough_engine campaign show <campaign_id>

# List evaluation packs
.venv/bin/python -m breakthrough_engine evaluation-pack list

# Export pack for campaign
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine evaluation-pack export <campaign_id>

# Check pack integrity (v002)
python3 -c "
import json, glob
packs = sorted(glob.glob('runtime/evaluation_packs/*/evaluation_pack.json'))
for path in packs:
    with open(path) as f: p = json.load(f)
    diag = p.get('accounting_diagnostics', {})
    cid = p['campaign']['campaign_id']
    ok = diag.get('integrity_ok', 'N/A (v001)')
    elapsed = p['campaign']['elapsed_seconds']
    print(f'{cid[:16]}  schema={p.get(\"schema_version\",\"v001\")}  integrity={ok}  elapsed={elapsed:.0f}s')
"

# View finalist table for a campaign
python3 -c "
import json
with open('runtime/evaluation_packs/<campaign_id>/evaluation_pack.json') as f:
    p = json.load(f)
for entry in p.get('tiebreak_notes', {}).get('ranked_finalists', [])[:10]:
    print(f\"{entry['rank']:2d}. {entry['final_score']:.3f}  {entry['title'][:55]}\")
"
```

---

## Remaining Limitations

1. `total_candidates_blocked` in older packs (v001) will still show 0 — re-export to get correct count
2. `champion_rationale` from DailySearchLadder is short ("Stage 1 abandoned — ...", "Highest score") — not a rich narrative, but it's the programmatic rationale that was always there
3. Evidence-strength calibration is not retroactive — Phase 7A/7B campaign scores are unchanged
4. Falsification is still only run on shortlisted (top-3) candidates — many finalists will show `MISSING` in long overnight runs until Stage 3 falsification is expanded
