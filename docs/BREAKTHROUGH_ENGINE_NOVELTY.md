# Breakthrough Engine -- Novelty Engine

## Overview

The novelty engine evaluates each candidate hypothesis against prior art using layered deterministic heuristics. Before a candidate can proceed to scoring, it must pass a novelty gate that checks for duplicates and substantial overlap with existing published work. This ensures the engine only promotes genuinely novel ideas.

**Module:** `breakthrough_engine/novelty.py`

## Data Models

### NoveltyResult

Each novelty evaluation produces a `NoveltyResult` with the following fields:

| Field                | Type                | Description                                                |
|----------------------|---------------------|------------------------------------------------------------|
| `candidate_id`       | `str`               | ID of the candidate being evaluated                        |
| `novelty_score`      | `float`             | Overall novelty score (0.0 = duplicate, 1.0 = fully novel) |
| `duplicate_risk_score` | `float`           | Inverse measure -- how likely this is a duplicate          |
| `prior_art_hits`     | `list[PriorArtHit]` | Matched prior art entries                                  |
| `overlap_reasons`    | `list[str]`         | Human-readable descriptions of each overlap detected       |
| `decision`           | `str`               | One of `pass`, `warn`, or `fail`                           |
| `warnings`           | `list[str]`         | Non-fatal concerns for reviewer attention                  |
| `explanation`        | `str`               | Full human-readable trace of the evaluation                |

### PriorArtHit

Each match against existing work is represented as a `PriorArtHit`:

| Field          | Type    | Description                                      |
|----------------|---------|--------------------------------------------------|
| `source`       | `str`   | Origin of the prior art (e.g., OpenAlex, internal) |
| `source_id`    | `str`   | Identifier within that source                    |
| `title`        | `str`   | Title of the matched work                        |
| `similarity`   | `float` | Similarity score between candidate and match     |
| `overlap_type` | `str`   | Category of overlap detected                     |

## Evaluation Layers

The novelty check applies four layers in sequence. Each layer uses a deterministic heuristic with a fixed threshold:

### Layer 1 -- Exact Title Match (threshold: 0.95)

Compares the candidate title against all known prior art titles. A similarity score at or above 0.95 indicates a near-exact duplicate.

**Decision:** hard-fail

### Layer 2 -- Statement Overlap (threshold: 0.80)

Compares the candidate's core statement or thesis against statements in prior work. Catches cases where titles differ but the underlying claim is the same.

**Decision:** hard-fail

### Layer 3 -- Mechanism Overlap (threshold: 0.75)

Checks whether the proposed mechanism or method substantially overlaps with existing approaches, even when the framing and claims differ.

**Decision:** warn

### Layer 4 -- Keyword Overlap with Retrieved Papers (thresholds: 0.60 warn, 0.70 fail)

Analyzes keyword and concept overlap between the candidate and papers retrieved from external sources. Two thresholds apply:

- **0.60:** triggers a warning
- **0.70:** triggers a fail

## Decision Logic

The final decision is determined by the most severe outcome across all layers:

1. **fail** -- Any layer produces a hard-fail (exact title match, statement overlap, or keyword overlap above 0.70). The candidate is rejected.
2. **warn** -- No hard-fail, but mechanism overlap or keyword overlap above 0.60 is detected. The candidate proceeds with warnings attached.
3. **pass** -- No overlap exceeds any threshold. The candidate is considered novel.

## Persistence

All novelty check results are persisted to the `bt_novelty_checks` table. This provides an audit trail of every evaluation and supports retrospective analysis of how novelty decisions were made.

## Position in the Pipeline

The novelty gate runs in the orchestrator pipeline between the evidence gate and scoring:

```
candidate generation → evidence gate → novelty gate → scoring → publication
```

A candidate that fails the novelty gate does not proceed to scoring.

## Explainability

Two fields on `NoveltyResult` provide human-readable traces:

- **`overlap_reasons`** -- A list of specific reasons overlap was detected, one per layer that triggered. Each entry identifies the source, the type of overlap, and the similarity score.
- **`explanation`** -- A single narrative string summarizing the full evaluation, suitable for display in review interfaces or logs.

These fields ensure that every novelty decision can be understood and audited without re-running the evaluation.
