# Breakthrough Engine Evaluation Profile Standard

**Phase**: 7D
**Date**: 2026-03-09
**Branch**: breakthrough-engine-phase7d-eval-profile

---

## Overview

The evaluation profile (`eval_clean_energy_30m`) is the reference-grade campaign profile
for scientific comparison and Bayesian policy optimization. It differs from smoke and
overnight profiles in that it:

1. Requires full finalist falsification (not just top-K shortlisted)
2. Requires integrity_ok = True before pack export completes
3. Uses strict falsification mode
4. Has stable budgets for cross-batch comparison
5. Is the only profile suitable for policy learning input

---

## Profile Comparison

| Property | smoke_10m | pilot_30m | overnight_clean_energy | **eval_clean_energy_30m** |
|----------|-----------|-----------|----------------------|--------------------------|
| profile_type | smoke | pilot | overnight | **evaluation** |
| wall_clock_budget_minutes | 10 | 30 | 480 | **30** |
| stage2_shortlist_size | 2 | 3 | 5 | **8** |
| stage3.max_trials | 2 | 3 | 5 | **10** |
| falsify_all_finalists | false | false | false | **true** |
| falsification.strict_mode | false | false | true | **true** |
| integrity required | no | no | no | **yes (hard fail)** |
| profile_type gating | none | none | none | **evaluation-grade** |
| review labels | optional | optional | optional | **expected** |
| cross-batch comparable | no | no | no | **yes** |

---

## Stability Guarantees

The eval_clean_energy_30m profile defines stable budget parameters so that campaigns
from different batches can be compared scientifically:

- `wall_clock_budget_minutes: 30` — consistent time budget
- `candidate_trial_budget: 10` — consistent candidate budget
- `stage2_shortlist_size: 8` — large enough to pass all typical finalists to stage 3
- `stage3.max_trials: 10` — enough to cover all finalists
- `falsify_all_finalists: true` — all finalists always get falsification
- Domain fixed to `clean-energy` / `clean_energy_shadow` program

These parameters are intentionally kept stable to enable multi-batch comparison.
Do not change them between batches unless making a documented policy change.

---

## Integrity Requirements

For evaluation-grade campaigns, the evaluation pack exporter raises `ValueError` if
any of these conditions are not met:

1. `elapsed_seconds > 0` for completed campaigns
2. `champion_rationale` is non-empty
3. No finalists with `falsification_risk == "MISSING"`
4. No `generated_count_mismatch` in accounting_diagnostics
5. `ladder_campaign_id` recovered from stage_events

The `integrity_ok` flag must be `True` before the pack is written.

---

## Review Labels

Evaluation-grade campaigns include structured human review labels for champion and
runner-up finalists. Labels are captured after pack export and stored in `bt_review_labels`.

See: `BREAKTHROUGH_ENGINE_REVIEW_LABELS.md`

---

## How to Run an Evaluation-Grade Campaign

```bash
cd /Users/openclaw/breakthrough-engine

# Run with evaluation profile
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine campaign run \
    --profile eval_clean_energy_30m \
    --strict

# Export evaluation pack (must reach integrity_ok=True)
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine evaluation-pack export <campaign_id> --overwrite

# Check integrity
python3 -c "
import json
with open('runtime/evaluation_packs/<campaign_id>/evaluation_pack.json') as f:
    p = json.load(f)
diag = p.get('accounting_diagnostics', {})
print('Integrity OK:', diag.get('integrity_ok'))
print('Schema:', p.get('schema_version'))
for issue in diag.get('issues', []):
    print('ISSUE:', issue)
"
```

---

## Schema Version

| Profile | Schema Version |
|---------|---------------|
| smoke_10m | v002 |
| pilot_30m | v002 |
| overnight_clean_energy | v002 |
| eval_clean_energy_30m | v003 |

v003 adds:
- `review_labels` section in pack JSON
- Hard integrity gate (ValueError on failure)
- `falsification_complete` flag in accounting_diagnostics
