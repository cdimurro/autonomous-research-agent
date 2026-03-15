# Breakthrough Engine - Architecture (Legacy Reference)

> **Note:** This document describes the broad-engine hypothesis pipeline architecture.
> For the current architecture including benchmark domains (PV, battery), unified
> contracts, and policy system, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Module Map

```
breakthrough_engine/
  __init__.py
  models.py              # Pydantic domain models + lifecycle enums
  db.py                  # Database init, migrations, repository layer
  config_loader.py       # Research program YAML loader
  harnesses.py           # Four deterministic harnesses
  scoring.py             # Candidate scoring logic (explicit formula)
  candidate_generator.py # Provider abstraction for generation
  evidence_source.py     # Evidence ingestion boundary / adapters
  simulator.py           # Simulator adapter layer
  orchestrator.py        # Daily cycle orchestrator
  api.py                 # Flask blueprint for API routes
  cli.py                 # CLI entrypoints
  reporting.py           # Report generation (JSON + Markdown)
  memory.py              # Cross-run duplicate detection + learning
```

## Run Modes

| Mode | Candidate Generator | Simulator | DB | Use Case |
|------|--------------------|-----------|----|----------|
| `deterministic_test` | Fake (fixed output) | MockSimulator | In-memory SQLite | Pytest, CI |
| `demo_local` | Fake (varied output) | MockSimulator | File SQLite | Local demos |
| `production_local` | LLM (Ollama) | MockSimulator (v1) | File SQLite | Real daily runs |
| `omniverse_stub` | LLM (Ollama) | OmniverseAdapter | File SQLite | Future integration |

## Candidate Lifecycle States

```
generated
  |---> dedup_rejected        (near-duplicate of prior candidate)
  |---> hypothesis_failed     (failed HypothesisLegalityHarness)
  |---> evidence_failed       (failed EvidenceLegalityHarness)
  |---> simulation_failed     (failed SimulationLegalityHarness or simulator error)
  |---> publication_failed    (failed PublicationGateHarness or below threshold)
  |---> finalist              (passed all gates but not the top candidate)
  \---> published             (top candidate, published for this run)
```

Every non-published candidate has a recorded rejection reason with the harness decision that caused it.

## Run Lifecycle States

```
started
  |---> completed                (one candidate published)
  |---> completed_no_publication (all candidates rejected or below threshold)
  \---> failed                   (unhandled error during orchestration)
```

## Data Model

### Core Entities

- **ResearchProgram** - YAML-defined domain config (budget, thresholds, constraints)
- **CandidateHypothesis** - Generated hypothesis with mechanism, outcome, assumptions
- **EvidenceItem** - Single piece of evidence with source and quote
- **EvidencePack** - Collection of evidence items for a candidate
- **SimulationSpec** - What to simulate, parameters, constraints
- **SimulationResult** - Outcome of simulation run
- **HarnessDecision** - Structured pass/fail from a harness gate
- **CandidateScore** - Multi-dimensional scoring breakdown
- **PublicationRecord** - Published breakthrough candidate with full provenance
- **RunRecord** - Single orchestration run metadata
- **RejectedCandidateRecord** - Why a candidate was rejected

## Database Tables (added to existing scires.db)

- `bt_schema_version` - Migration version tracking
- `bt_runs` - Run records with lifecycle state
- `bt_candidates` - All generated candidates with lifecycle state
- `bt_evidence_items` - Evidence items
- `bt_evidence_packs` - Evidence pack metadata
- `bt_simulation_specs` - Simulation specifications
- `bt_simulation_results` - Simulation outcomes
- `bt_harness_decisions` - All harness gate decisions
- `bt_scores` - Score breakdowns
- `bt_publications` - Published candidates (one per run max)
- `bt_rejections` - Rejected candidates with reasons and harness output

All tables prefixed with `bt_` to avoid collision with existing tables.

### Migration Strategy

- `bt_schema_version` table tracks which migrations have been applied
- Each migration is a numbered function (v001, v002, ...)
- `db.init_db()` is idempotent: safe to run multiple times
- Never DROP or ALTER existing (non-bt_) tables
- New migrations are append-only

## Evidence Ingestion Boundary

`evidence_source.py` provides a first-class interface for evidence retrieval:

```
EvidenceSource (ABC)
  |-- ExistingFindingsSource   (reads from scires.db findings table)
  |-- DemoFixtureSource        (returns hardcoded fixtures for demos/tests)
  |-- FutureRetrievalSource    (stub for future literature search APIs)
```

The orchestrator calls `evidence_source.gather()` and receives a list of `EvidenceItem` objects. This keeps evidence ingestion cleanly separated from orchestration logic.

## Scoring Formula (v1)

```
final_score = (
    novelty_score          * 0.20 +
    plausibility_score     * 0.20 +
    impact_score           * 0.20 +
    evidence_strength      * 0.20 +
    simulation_readiness   * 0.10 +
    (1 - validation_cost)  * 0.10
)
```

Tie-break order: publication gate pass > evidence_strength > lower validation_cost > earlier candidate_id.

Publication threshold: >= 0.60 (configurable per research program).

## Execution Flow

```
1. Load ResearchProgram from YAML
2. Initialize run record (status: started)
3. Gather seed evidence via EvidenceSource adapter
4. Generate N candidate hypotheses (status: generated)
5. Deduplicate against prior candidates (rejected -> dedup_rejected)
6. Run HypothesisLegalityHarness (rejected -> hypothesis_failed)
7. Assemble EvidencePacks for passing candidates
8. Run EvidenceLegalityHarness (rejected -> evidence_failed)
9. Rank and select top K by CandidateScore
10. Build SimulationSpecs for top K
11. Run SimulationLegalityHarness (rejected -> simulation_failed)
12. Execute SimulatorAdapter (mock or real)
13. Final scoring with simulation results
14. Run PublicationGateHarness (rejected -> publication_failed)
15. Select single best passing candidate -> published
16. Mark remaining passing candidates -> finalist
17. Persist publication record
18. Persist all rejected candidates with reasons
19. Update run record (completed | completed_no_publication)
20. Generate JSON + Markdown reports
```

## API Routes

- `GET  /api/breakthrough/health` - Health check
- `POST /api/breakthrough/run` - Trigger a breakthrough cycle
- `GET  /api/breakthrough/runs` - List all runs
- `GET  /api/breakthrough/runs/<id>` - Run details
- `GET  /api/breakthrough/publications` - List publications
- `GET  /api/breakthrough/publications/<id>` - Publication detail
- `GET  /api/breakthrough/rejections/<run_id>` - Rejected candidates
- `GET  /api/breakthrough/programs` - Available research programs

## Simulator Integration

```
SimulatorAdapter (ABC)
  |-- MockSimulatorAdapter (deterministic, for tests/demos)
  |-- OmniverseSimulatorAdapter (stub, future integration)
```

## Publication Model

Every published candidate includes:
- status_label: "validated_breakthrough_candidate" (never "confirmed discovery")
- Full hypothesis text
- Evidence summary with citations
- Simulation summary (or "not simulated")
- Assumptions disclosed
- Uncertainties disclosed
- Score breakdown
- Replication priority

One publication per run maximum. All other candidates are archived as finalists or rejected.
