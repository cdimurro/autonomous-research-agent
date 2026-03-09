# Campaign Analysis Schema

**Version**: v001
**Module**: `breakthrough_engine.evaluation_pack`
**Storage**: `runtime/evaluation_packs/<campaign_id>/`

## Purpose

Defines the canonical structured output format for Breakthrough Engine campaign analysis.
Designed for external analysis by humans or AI (e.g., ChatGPT).
All future campaigns will produce this schema automatically.

## Output Files

| File | Format | Contents |
|------|--------|----------|
| `evaluation_pack.json` | JSON | Complete structured pack (all fields) |
| `evaluation_pack.md` | Markdown | Human-readable summary |
| `candidates.csv` | CSV | All candidates with scores (1 row/candidate) |
| `finalists.csv` | CSV | Finalist candidates with full text |

## JSON Schema: Top-Level Structure

```json
{
  "schema_version": "v001",
  "campaign": { ... },          // Campaign identity and lifecycle
  "config": { ... },            // Configuration snapshot
  "models": { ... },            // AI models used
  "statistics": { ... },        // Candidate counts
  "champion": { ... },          // Champion candidate with full data
  "champion_rationale": "...",  // Why this candidate won
  "tiebreak_notes": { ... },    // Ranking rationale for finalists
  "preflight": { ... },         // Preflight health summary
  "stage_events": [ ... ],      // Stage timing and retries
  "finalists": [ ... ],         // All finalist candidates
  "all_candidates": [ ... ],    // All candidates (finalists + generated)
  "runs": [ ... ],              // Underlying run records
  "posteriors": [ ... ]         // Bayesian posterior snapshot
}
```

## campaign Object

| Field | Type | Description |
|-------|------|-------------|
| campaign_id | string | Unique campaign identifier (hex) |
| daily_campaign_id | string | Inner DailySearchLadder campaign ID |
| profile_name | string | e.g. "overnight_clean_energy" |
| profile_type | string | "pilot", "overnight", or "smoke" |
| status | string | See Campaign Outcome Categories |
| started_at | ISO-8601 string | UTC start time |
| completed_at | ISO-8601 string | UTC completion time |
| elapsed_seconds | float | Total elapsed time in seconds |

## config Object

| Field | Type | Description |
|-------|------|-------------|
| domain | string | e.g. "clean-energy" |
| program_name | string | e.g. "clean_energy_shadow" |
| mode | string | e.g. "production" |
| wall_clock_budget_minutes | int | Max runtime budget |
| candidate_trial_budget | int | Max candidate count budget |

## models Object

| Field | Type | Description |
|-------|------|-------------|
| generation_model | string | LLM used for hypothesis generation |
| embedding_provider | string | "OllamaEmbeddingProvider(X)" or "MockEmbeddingProvider" |
| embedding_model | string | Model name or "mock" |
| policy_used | string | Bayesian policy for champion selection |

## statistics Object

| Field | Type | Description |
|-------|------|-------------|
| total_candidates_generated | int | Total hypotheses generated |
| total_candidates_blocked | int | Blocked by novelty/other gates |
| total_shortlisted | int | Passed to stage 2 |
| total_finalists | int | Reached finalist stage |
| total_runs | int | Number of underlying run executions |

## Candidate Record (in finalists / all_candidates)

| Field | Type | Description |
|-------|------|-------------|
| candidate_id | string | Unique ID |
| run_id | string | Which run produced this candidate |
| title | string | Short descriptive title (max 80 chars) |
| domain | string | Scientific domain |
| statement | string | Clear, testable hypothesis statement |
| mechanism | string | Physical/chemical/biological mechanism |
| expected_outcome | string | Measurable expected result |
| testability_window_hours | float | Hours to validate |
| novelty_notes | string | What makes this novel |
| assumptions | list[string] | Key assumptions |
| risk_flags | list[string] | Key risks |
| evidence_refs | list[string] | Evidence item IDs |
| status | string | "finalist", "generated", "rejected" |
| created_at | ISO-8601 string | When created |
| scores.final | float | Overall composite score (0.0–1.0) |
| scores.novelty | float | Prior-art novelty score |
| scores.plausibility | float | Scientific plausibility |
| scores.impact | float | Potential impact |
| scores.validation_cost | float | Cost/ease to validate |
| scores.evidence_strength | float | Supporting evidence quality |
| scores.simulation_readiness | float | Ready for simulation |
| falsification.risk | string | "low", "medium", "high" |
| falsification.passed | bool | Passed falsification gate |
| falsification.assumption_fragility_score | float | 0.0–1.0 |
| falsification.reasoning | string | Human-readable summary |

## tiebreak_notes Object

```json
{
  "ranked_finalists": [
    {
      "rank": 1,
      "candidate_id": "...",
      "title": "...",
      "final_score": 0.947,
      "is_champion": true,
      "why_ranked_here": "..."
    }
  ],
  "tiebreak_dimension": "simulation_readiness_score",
  "selection_basis": "highest final_score with simulation_readiness_score as tiebreak"
}
```

## CSV: candidates.csv columns

```
candidate_id, run_id, title, domain, status,
final_score, novelty_score, plausibility_score, impact_score,
validation_cost_score, evidence_strength_score, simulation_readiness_score,
falsification_risk, falsification_passed, assumption_fragility_score,
testability_window_hours, evidence_refs, created_at
```

## CSV: finalists.csv columns

Same as candidates.csv plus:
```
statement, mechanism
```

## Campaign Outcome Categories

| Status | Meaning |
|--------|---------|
| completed_with_draft | Success — champion candidate produced |
| completed_no_draft | Pipeline ran, no candidate met threshold |
| aborted_preflight | Pre-launch checks failed |
| aborted_runtime | Execution failed |
| aborted_timeout | Wall-clock budget exceeded |
| aborted_signal | Clean shutdown via SIGTERM/SIGINT |

## Cross-Campaign Analysis

To compare multiple campaigns:

```python
import json, glob, os
packs = []
for path in glob.glob("runtime/evaluation_packs/*/evaluation_pack.json"):
    with open(path) as f:
        packs.append(json.load(f))

# Compare champion scores across campaigns
for p in packs:
    c = p["campaign"]
    ch = p.get("champion", {})
    score = ch.get("scores", {}).get("final", "N/A")
    emb = p["models"]["embedding_provider"]
    print(f"{c['campaign_id'][:8]}  {c['status']:25s}  champion_score={score}  embedding={emb}")
```

## Exporting

```bash
# Export one campaign
.venv/bin/python -m breakthrough_engine evaluation-pack export <CAMPAIGN_ID>

# Export with overwrite
.venv/bin/python -m breakthrough_engine evaluation-pack export <CAMPAIGN_ID> --overwrite

# List all evaluation packs
.venv/bin/python -m breakthrough_engine evaluation-pack list
```
