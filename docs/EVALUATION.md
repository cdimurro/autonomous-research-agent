# Evaluation Architecture

This document explains how the system evaluates scientific claims — the core of what makes this project different from a standard paper-ingestion pipeline.

## The Problem

LLMs extract plausible-sounding structured data from papers. But "plausible-sounding" is not the same as "correct." A model can fabricate a quote that looks real, assign a metric value outside physical bounds, or report high confidence on a claim with no supporting evidence.

This system treats LLM extraction as an *untrusted source* and validates everything it produces.

## Two-Layer Evaluation

Every extracted finding passes through two independent evaluation layers before it enters the knowledge graph.

### Layer 1: Confidence Scoring (`judge-score.sh`)

A weighted composite score from five factors:

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Source quality | 0.20 | Journal tier (Nature=0.95, arXiv=0.65) |
| Extraction quality | 0.25 | Parser tier + structured data completeness |
| Numeric validation | 0.25 | Deterministic range checks against `config/validators.yaml` |
| Hallucination check | 0.15 | Fuzzy match of provenance quote against source text |
| Cross-reference | 0.15 | Corroboration by other papers (default 0.5 until populated) |

**Output**: A 0–1 confidence score and a verdict:
- `accepted` (score >= 0.60)
- `revised` (0.25–0.60)
- `rejected` (< 0.25, or hallucination score < 0.5)

Weights and thresholds are configurable in `config/confidence.yaml`.

### Layer 2: Rubric Grading (`rubric-grade.sh`)

Runs *after* confidence scoring. Converts each accepted/revised finding into a `ScientificConclusionCandidate` artifact and grades it against a decomposed rubric.

The default rubric (`scientific_conclusion_v1`) has 7 criteria, 10 total points, and a pass threshold of 6:

| Criterion | Points | Logic |
|-----------|--------|-------|
| `evidence_support` | 2 | Structured data has both metric and value |
| `provenance_support` | 2 | Provenance quote present and >= 30 chars |
| `numeric_consistency` | 2 | All domain validators pass |
| `unit_consistency` | 1 | Reported unit matches expected unit for the metric |
| `contradiction_awareness` | 1 | Content references the reported metric/value |
| `uncertainty_calibration` | 1 | High confidence requires strong evidence factors |
| `conclusion_alignment` | 1 | Textual content mentions the structured metric or value |

**All grading logic is deterministic.** No LLM is involved in evaluation.

Each rubric item produces:
- A score (0 to max_points)
- A pass/fail flag
- Machine-readable failure tags (e.g., `missing_provenance`, `range_violation`, `overconfident`)
- A human-readable rationale
- References to evidence used

## Artifact Flow

```
findings table (from LLM extraction)
  │
  ▼
judge-score.sh
  ├── Deterministic numeric validation → verification_results table
  ├── Hallucination check (quote fuzzy match)
  ├── Confidence score computation → confidence_scores table
  └── Verdict: accepted / revised / rejected → findings.judge_verdict
  │
  ▼
rubric-grade.sh (for accepted + revised findings)
  ├── Build ScientificConclusionCandidate from finding + validators + confidence
  ├── Grade each rubric item independently
  ├── Compute total score and pass/fail
  ├── Persist → rubric_results table
  └── Write JSON artifact → runtime/evaluations/<finding_id>.rubric.json
```

## Artifact Contracts

Three JSON Schemas in `schemas/` define the evaluation artifacts:

**`ScientificConclusionCandidate`** — The input to rubric grading. Assembles a finding with its provenance, validator results, and confidence context into a single auditable object.

**`RubricResult`** — The complete output of rubric grading. Includes the rubric ID/version, total score, pass/fail, grader metadata, and the array of per-item results.

**`RubricItemResult`** — A single rubric criterion's result. Includes score, failure tags, rationale, and evidence references.

These schemas are documentation and validation contracts — they define what the grader must produce.

## Persistence

Rubric results are stored in two places:

1. **`rubric_results` table** in SQLite — queryable, indexed by `artifact_id` and `passed`. The `item_results_json` column stores the full per-item breakdown.

2. **JSON artifacts** in `runtime/evaluations/` — one file per graded finding, named `<finding_id>.rubric.json`. These are the primary debugging and inspection artifacts.

## Extending the Rubric

To add a new rubric criterion:

1. Add the item definition to `config/rubrics.yaml` (name, max_points, requires)
2. Update `max_score` to reflect the new total
3. Add grading logic for the new `item_id` in `scripts/rubric-grade.sh`
4. Add test cases in `tests/test-rubric-grading.sh`

To add a new rubric entirely (e.g., for hypothesis evaluation):

1. Add a new rubric block under `rubrics:` in `config/rubrics.yaml`
2. Add a grading code path in `rubric-grade.sh` that selects the rubric by ID
3. Define any new artifact schemas in `schemas/`

## What This Does Not Do

- **Evaluate scientific truth.** The rubric checks whether a claim is well-evidenced and internally consistent, not whether it's correct.
- **Use LLM judgment for scoring.** All evaluation logic is deterministic. The LLM is used only for extraction.
- **Replace peer review.** This is a quality filter for automated extraction, not a substitute for human scientific evaluation.
