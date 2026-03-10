# Phase 7C Batch Results

**Branch**: `breakthrough-engine-phase7c-telemetry-calibration`
**Date**: 2026-03-09/10
**Phase**: 7C-B (strict validation + 5-campaign batch)

---

## Summary

| Item | Result |
|------|--------|
| Pack v002 verification (Phase A) | PASS |
| Strict validation campaign (Phase B) | PASS |
| 5-campaign clean-energy batch (Phase C) | PASS — all 5 completed_with_draft |
| Blocker fixes | 1 minimal fix (run timestamp normalization) |
| New tests added | 2 (TestRunTimestampNormalization) |
| Total tests | 581 passing, 0 failures |

---

## Batch Campaigns (Phase C)

| # | Campaign ID | Status | Elapsed | Champion Score | Champion Title |
|---|-------------|--------|---------|----------------|----------------|
| 1 | 338e0f4f25104af9 | completed_with_draft | 507s | 0.8740 | Hybrid Electrolyte-Photocatalytic Interface for Tandem Water Splitting |
| 2 | 715d90d816c74256 | completed_with_draft | 540s | 0.9155 | Anion Exchange Membrane Cross-Linking for Seawater Resistance |
| 3 | e415af49809b492b | completed_with_draft | 481s | 0.9205 | High-Energy Solid-State Battery Integration for Offshore Wake Stabilization |
| 4 | eaecd0ac79724763 | completed_with_draft | 540s | 0.8830 | Piezo-Electric Wake Shielding Using Sulfide-Based Nanocomposites |
| 5 | 7ba8ad82393a4376 | completed_with_draft | 542s | 0.9075 | CO2-Derived Carbonate Precursors for Solid-State Battery Interfaces |

**Best campaign**: 3 (e415af49809b492b) — score 0.9205
**Weakest campaign**: 1 (338e0f4f25104af9) — score 0.8740

---

## Blocker Fix Applied

### Run Timestamp Normalization (7C-B)

**Issue**: Campaign 4 (eaecd0ac79724763) had a run that started at the exact same second as the campaign (`2026-03-09T23:57:47.318316` vs `2026-03-09T23:57:47Z`). SQLite string comparison `.318316 < Z` caused the run to be excluded from the window query, so the champion was missing from the pack.

**Fix**: Changed the run-matching query to normalize timestamps to 19-char seconds precision:
```sql
-- Before:
WHERE started_at >= ? AND started_at <= ?

-- After:
WHERE substr(started_at, 1, 19) >= substr(?, 1, 19)
  AND substr(started_at, 1, 19) <= substr(?, 1, 19)
```

**Tests**: `TestRunTimestampNormalization` (2 tests) added to `tests/test_breakthrough/test_phase7c.py`

**Files changed**: `breakthrough_engine/evaluation_pack.py` (1 query change, 6-line comment)

---

## Batch Artifacts

```
runtime/evaluation_batches/phase7c_batch_20260309/
  batch_summary.json        # Full machine-readable batch summary
  batch_summary.md          # Human-readable batch report
  campaign_metrics.csv      # Per-campaign KPIs
  champions.csv             # Champion title/score/rationale per campaign
  finalists_combined.csv    # All 30 finalists across 5 campaigns

runtime/evaluation_packs/
  338e0f4f25104af9/         # Batch campaign 1
  715d90d816c74256/         # Batch campaign 2
  e415af49809b492b/         # Batch campaign 3
  eaecd0ac79724763/         # Batch campaign 4
  7ba8ad82393a4376/         # Batch campaign 5
  2bfaec77b7314b6a/         # Validation campaign (Phase B)
  f01a0a7c72304481/         # Phase 7B reference campaign (re-exported with v002)
```

---

## Morning-After Inspection Commands

### List campaigns

```bash
# All campaigns
.venv/bin/python -m breakthrough_engine campaign list

# Just batch campaigns
python3 -c "
import json
for cid in ['338e0f4f25104af9','715d90d816c74256','e415af49809b492b','eaecd0ac79724763','7ba8ad82393a4376']:
    with open(f'runtime/evaluation_packs/{cid}/evaluation_pack.json') as f:
        p = json.load(f)
    c = p['campaign']
    print(f'{cid}  {c[\"elapsed_seconds\"]:.0f}s  {p.get(\"champion\",{}).get(\"title\",\"\")[:50]}')
"
```

### Show a campaign

```bash
# Quick look at one campaign's pack
python3 -c "
import json
with open('runtime/evaluation_packs/e415af49809b492b/evaluation_pack.json') as f:
    p = json.load(f)
print('Schema:', p['schema_version'])
print('Status:', p['campaign']['status'])
print('Elapsed:', p['campaign']['elapsed_seconds'], 's')
print('Champion:', p.get('champion',{}).get('title'))
print('Score:', p.get('champion',{}).get('scores',{}).get('final'))
diag = p.get('accounting_diagnostics', {})
print('Integrity OK:', diag.get('integrity_ok'))
print('Issues:', diag.get('issues', []))
"
```

### Locate evaluation packs

```bash
ls runtime/evaluation_packs/
# Each has: evaluation_pack.json, evaluation_pack.md, finalists.csv, candidates.csv
```

### Check all packs integrity at a glance

```bash
python3 -c "
import json, glob
packs = sorted(glob.glob('runtime/evaluation_packs/*/evaluation_pack.json'))
for path in packs:
    with open(path) as f: p = json.load(f)
    diag = p.get('accounting_diagnostics', {})
    cid = p['campaign']['campaign_id']
    ok = diag.get('integrity_ok', 'N/A')
    elapsed = p['campaign']['elapsed_seconds']
    champ = p.get('champion', {}).get('title', '')[:40]
    score = p.get('champion', {}).get('scores', {}).get('final', '')
    print(f'{cid[:16]}  schema={p.get(\"schema_version\",\"v001\")}  integrity={ok}  elapsed={elapsed:.0f}s  score={score}  {champ}')
"
```

### Inspect champion packet

```bash
python3 -c "
import json
with open('runtime/evaluation_packs/e415af49809b492b/evaluation_pack.json') as f:
    p = json.load(f)
champ = p.get('champion', {})
print('Title:', champ.get('title'))
print('Statement:', champ.get('statement'))
print('Mechanism:', champ.get('mechanism'))
print('Expected Outcome:', champ.get('expected_outcome'))
print('Scores:', json.dumps(champ.get('scores', {}), indent=2))
falsi = champ.get('falsification', {})
print('Falsification:', falsi)
print('Rationale:', p.get('champion_rationale'))
"
```

### Inspect finalist CSVs

```bash
# Show all batch finalists (combined)
head -5 runtime/evaluation_batches/phase7c_batch_20260309/finalists_combined.csv
wc -l runtime/evaluation_batches/phase7c_batch_20260309/finalists_combined.csv

# Show champions across batch
cat runtime/evaluation_batches/phase7c_batch_20260309/champions.csv

# Campaign metrics
cat runtime/evaluation_batches/phase7c_batch_20260309/campaign_metrics.csv
```

### Verify real embeddings were used

```bash
python3 -c "
import json, glob
for path in sorted(glob.glob('runtime/evaluation_packs/*/evaluation_pack.json')):
    with open(path) as f: p = json.load(f)
    cid = p['campaign']['campaign_id']
    provider = p.get('models', {}).get('embedding_provider', 'UNKNOWN')
    print(f'{cid[:16]}  {provider}')
"
```

### Browse the batch summary

```bash
cat runtime/evaluation_batches/phase7c_batch_20260309/batch_summary.md
# or open in editor:
open runtime/evaluation_batches/phase7c_batch_20260309/batch_summary.md
```

### Hand to ChatGPT

Recommended files to provide for analysis:
1. `runtime/evaluation_batches/phase7c_batch_20260309/batch_summary.json` — full batch data
2. `runtime/evaluation_batches/phase7c_batch_20260309/finalists_combined.csv` — all 30 finalists
3. `runtime/evaluation_batches/phase7c_batch_20260309/champions.csv` — 5 champions
4. Any individual `evaluation_pack.json` for per-campaign deep dive

---

## Test Summary

```bash
# Run full test suite
.venv/bin/python -m pytest tests/ -q

# Run Phase 7C tests only
.venv/bin/python -m pytest tests/test_breakthrough/test_phase7c.py -v

# Run the new timestamp normalization tests
.venv/bin/python -m pytest tests/test_breakthrough/test_phase7c.py::TestRunTimestampNormalization -v
```

**Result**: 581 passing, 0 failures (579 + 2 new from 7C-B)
