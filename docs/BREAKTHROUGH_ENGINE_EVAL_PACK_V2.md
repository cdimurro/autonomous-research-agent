# Evaluation Pack v002 Standard

**Phase**: 7C
**Date**: 2026-03-09
**Schema version**: `v002`

---

## Overview

Evaluation Pack v002 is the hardened analysis-ready format introduced in Phase 7C. It fixes all data-quality issues identified after the Phase 7B overnight campaigns.

---

## Changes from v001

| Area | v001 | v002 |
|------|------|------|
| `elapsed_seconds` source | bt_daily_campaigns (broken) | bt_campaign_receipts (correct) |
| `champion_rationale` | Always blank (ID mismatch) | Recovered via stage_events → ladder_campaign_id |
| `total_candidates_blocked` | Always 0 (never set) | Counted from NOVELTY_FAILED candidates in DB |
| `total_candidates_generated` | Estimate (trials × budget) | Counted from actual DB rows |
| Finalist falsification | Silently None | Explicit MISSING sentinel |
| `accounting_diagnostics` | Not present | New section with integrity_ok + issues |
| `validate_pack_integrity` | Not present | Called before export, logs failures |
| `evidence_strength` | Near-saturated for 2 refs | Count penalty applied |

---

## Pack Structure (v002)

```json
{
  "schema_version": "v002",
  "campaign": {
    "campaign_id": "...",
    "profile_name": "...",
    "profile_type": "overnight|pilot|smoke",
    "status": "completed_with_draft|completed_no_draft|...",
    "started_at": "ISO8601Z",
    "completed_at": "ISO8601Z",
    "elapsed_seconds": <non-zero for completed campaigns>
  },
  "config": { "domain", "program_name", "mode", "wall_clock_budget_minutes", "candidate_trial_budget" },
  "models": {
    "generation_model": "qwen3.5:9b-q4_K_M",
    "embedding_provider": "OllamaEmbeddingProvider(nomic-embed-text)",
    "embedding_model": "nomic-embed-text",
    "policy_used": "..."
  },
  "statistics": {
    "total_candidates_generated": <DB count>,
    "total_candidates_blocked": <NOVELTY_FAILED count>,
    "total_shortlisted": <from receipt>,
    "total_finalists": <DB count>,
    "total_runs": <run count>
  },
  "champion": { ... full candidate record ... },
  "champion_rationale": "<non-empty for completed runs with champion>",
  "tiebreak_notes": { "ranked_finalists": [...], "tiebreak_dimension": "...", "selection_basis": "..." },
  "accounting_diagnostics": {
    "source_campaign_id": "...",
    "ladder_campaign_id": "...",
    "receipt_generated": <receipt value>,
    "receipt_blocked": <receipt value>,
    "db_generated": <DB value>,
    "db_blocked": <DB value>,
    "db_finalists": <DB value>,
    "elapsed_seconds_source": "bt_campaign_receipts",
    "issues": [],
    "integrity_ok": true
  },
  "preflight": { "readiness_score", "pass_count", "warn_count", "fail_count" },
  "stage_events": [...],
  "finalists": [ { ... CandidateRecord.to_dict() ... } ],
  "all_candidates": [ ... ],
  "runs": [ ... ],
  "posteriors": [ ... ]
}
```

---

## Falsification sentinel values

| Value | Meaning |
|-------|---------|
| `"low"` / `"medium"` / `"high"` | Normal falsification result |
| `"MISSING"` | Finalist/champion with no falsification summary in DB — explicit gap |
| `null` | Non-finalist candidate with no falsification (expected, not a gap) |

---

## Accounting diagnostics integrity_ok flag

`integrity_ok = true` means:
- elapsed_seconds > 0 for completed campaigns
- champion_rationale is non-empty
- No finalists with MISSING falsification
- No significant count mismatches between receipt and DB
- ladder_campaign_id was recovered from stage_events

`integrity_ok = false` means at least one issue was found. Check the `issues` array.

---

## Export commands

```bash
# Export a specific campaign
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine evaluation-pack export <campaign_id>

# Re-export (overwrite existing)
BT_EMBEDDING_MODEL=nomic-embed-text \
  .venv/bin/python -m breakthrough_engine evaluation-pack export <campaign_id> --overwrite

# List all packs
.venv/bin/python -m breakthrough_engine evaluation-pack list

# Quick integrity check
python3 -c "
import json
with open('runtime/evaluation_packs/<campaign_id>/evaluation_pack.json') as f:
    p = json.load(f)
diag = p.get('accounting_diagnostics', {})
print('Schema:', p.get('schema_version'))
print('Integrity OK:', diag.get('integrity_ok'))
for issue in diag.get('issues', []):
    print('  ISSUE:', issue)
"
```

---

## Stability guarantee

From Phase 7C onward, v002 is the stable export format for multi-campaign analysis.
The `schema_version` field allows tools to detect format differences between v001 (Phase 7B) and v002 (Phase 7C+) packs.
