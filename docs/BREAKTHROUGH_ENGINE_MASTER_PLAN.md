# Breakthrough Engine - Master Plan

## Vision

A scientific discovery engine that continuously ingests scientific papers and recent advancements, identifies where potential breakthroughs can be made, and publishes one high-quality breakthrough candidate per run. Each candidate is validated using deterministic rules, cross-checked against existing literature, and includes full provenance, assumptions, uncertainty, and failure traces.

In production, the system runs daily, producing one published candidate per day. All other candidates from the same run are archived as rejected or non-published finalists with full reasoning.

## Goals

1. Generate many candidate hypotheses from retrieved evidence
2. Evaluate novelty/plausibility/impact/validation cost
3. Run deterministic legality and evidence gates
4. Generate simulation specs for top candidates
5. Run a simulator adapter layer (mock for v1, Omniverse stub for future)
6. Score publication readiness
7. Persist all artifacts in SQLite + structured files
8. Expose results through API and minimal browseable interface
9. Retain rejected candidates and failure reasons for learning/auditability

## Run Modes

The system supports four distinct run modes that control which components are real vs mocked:

| Mode | Candidate Generator | Simulator | DB | Use Case |
|------|--------------------|-----------|----|----------|
| `deterministic_test` | Fake (fixed output) | MockSimulator | In-memory SQLite | Pytest, CI |
| `demo_local` | Fake (varied output) | MockSimulator | File SQLite | Local demos, onboarding |
| `production_local` | LLM (Ollama) | MockSimulator (v1) | File SQLite | Real daily runs |
| `omniverse_stub` | LLM (Ollama) | OmniverseAdapter | File SQLite | Future integration testing |

Run mode is set via research program YAML or CLI flag. Test code must never blur into production behavior.

## v1 Scope (This Session)

- Strong domain model with Pydantic schemas
- SQLite persistence with new breakthrough-specific tables
- Four deterministic harnesses (hypothesis, evidence, simulation, publication)
- Research program YAML config loader
- Daily orchestration flow (one published candidate per run)
- Simulator adapter abstraction with mock implementation
- Omniverse adapter interface stub
- Publication layer
- Flask API extension with breakthrough routes
- CLI entrypoints
- Pytest test suite
- Documentation

## Architecture

The breakthrough engine is implemented as `breakthrough_engine/` Python package that:
- Sits alongside the existing shell-script pipeline
- Reuses the same SQLite database (adds new tables)
- Extends the existing Flask API
- Can consume hypotheses from the existing pipeline

## Implementation Phases

### Phase 1 - Foundation (docs + inspection) [DONE]
### Phase 2 - Domain Model + Persistence
### Phase 3 - Harnesses + Scoring
### Phase 4 - Simulator + Orchestrator
### Phase 5 - API + CLI + Views
### Phase 6 - Tests + Polish

## Constraints

- Local-first, no cloud credentials required for tests
- Deterministic gates (no LLM in evaluation path)
- All candidates labeled as "validated_breakthrough_candidate", never "confirmed discovery"
- Every rejection must have a recorded reason
- Physics violations are never allowed
- Fixed-budget execution mindset
- One published candidate per run; all others archived as rejected/finalist

## v1 Scoring Formula

### Weighted Score

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

All individual scores are normalized to [0.0, 1.0].

### Tie-Break Order

When two candidates have the same final_score (within 0.001):
1. Publication gate pass (passed > not passed)
2. Higher evidence_strength
3. Lower validation_cost (cheaper to validate wins)
4. Earlier candidate_id (deterministic fallback)

### Publication Threshold

A candidate must score >= 0.60 final_score to be eligible for publication. This threshold is configurable per research program.

## Database Migration Requirements

- Idempotent DB initialization: running init multiple times must be safe
- Schema version table (`bt_schema_version`) tracks applied migrations
- Safe upgrade path: new tables are added alongside existing scires.db tables
- No destructive migrations by default: never DROP or ALTER existing tables
- All breakthrough tables prefixed with `bt_` to avoid collision
- Migration functions are ordered and versioned (v001, v002, ...)

## Acceptance Criteria

1. Documented architecture and plan
2. Working database init/migration path (idempotent, versioned)
3. Daily breakthrough orchestration flow (one publication per run)
4. At least one deterministic end-to-end execution path using mocks
5. Persistent storage of publications and rejections
6. API routes working locally
7. Minimal browseable view or JSON inspection path
8. Tests covering harnesses + end-to-end flow
9. Updated docs explaining how to run it
10. Final status report

## Current Production State (Phase 7C, 2026-03-09)

The system has evolved significantly from the v1 scope above. Current state:

### Output model
One validated champion candidate per campaign run (not "1–3 per day"). The champion is the top-ranked finalist after multi-stage scoring, falsification, and tiebreaking. All other finalists are archived with full scores and rankings.

### Candidate labels
The label `validated_breakthrough_candidate` (in `models.py`, `db.py`, `harnesses.py`) remains correct — it means "evaluated and validated by deterministic harnesses", not "confirmed scientific discovery". This terminology has not drifted.

### Embeddings
Production mode uses OllamaEmbeddingProvider(nomic-embed-text). Set `BT_EMBEDDING_MODEL=nomic-embed-text` for real embeddings. Without this env var, MockEmbeddingProvider is used (with a warning in production modes).

### Evaluation packs
Each completed campaign can be exported as a structured evaluation_pack (schema v002 as of Phase 7C). The pack contains the champion, all finalists, scores, falsification summaries, tiebreak rationale, and telemetry integrity diagnostics.

### Campaign profiles
Three profiles: `pilot_30m` (30 min), `smoke_10m` (10 min), `overnight_clean_energy` (480 min/8hr). Run with:
```bash
BT_EMBEDDING_MODEL=nomic-embed-text .venv/bin/python -m breakthrough_engine campaign run --profile overnight_clean_energy
```

### Current phase
**Phase 7C**: Telemetry integrity hardening, scoring calibration, 5-campaign clean-energy evaluation batch.

## Future Backlog

- Real LLM-powered candidate generation (Ollama integration) ✓ DONE
- Omniverse simulator integration
- Advanced novelty graph logic
- Patent ingestion
- Robotic lab handoff protocols
- Adaptive harness self-rewrite
- Multi-domain cross-pollination
- Bayesian scoring updates
- Continuous learning from rejected candidates
