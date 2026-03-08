# Breakthrough Engine - Phase 2 Productionization Plan

## Objective

Upgrade v1 from a demo-quality vertical slice into a more production-capable local system.

## Baseline (v1 state at start of Phase 2)

- 13 Python modules in `breakthrough_engine/`
- 88 passing tests, 0 failing
- 12 `bt_`-prefixed SQLite tables with versioned migrations
- Fake/Demo candidate generators (no real LLM)
- DemoFixtureSource + ExistingFindingsSource (wired but untested with real data)
- MockSimulatorAdapter + OmniverseAdapter stub (raises NotImplementedError)
- Flask Blueprint API with 12 routes + 2 HTML views
- 7 CLI commands
- JSON + Markdown report generation

## Phase 2 Deliverables

### Priority 1: Real Generation + Evidence

**A. OllamaCandidateGenerator**
- Real candidate generation via local Ollama API
- Structured JSON output parsing with fallback/repair
- Configurable model, temperature, prompt template, timeout
- Deterministic test mode via fixture responses
- Preserves existing ABC/provider abstraction

**B. ExistingFindingsSource Enhancement**
- Domain/program filtering
- Recency filtering
- Confidence threshold filtering
- Logging of findings retrieved/skipped/mapped
- Graceful handling of missing fields

### Priority 2: Benchmark + Regression

**C. Benchmark Fixtures + Regression Harness**
- Golden test cases: high-quality, generic, duplicate, evidence-poor, overconfident, simulation-unready, publishable, no-publication
- Deterministic regression harness verifying score ranges, publication behavior, one-pub-per-run invariant
- CLI command: `python -m breakthrough_engine benchmark run`

### Priority 3: Scheduler Hardening

**D. Scheduler Runner**
- Lock-file overlap protection
- Structured exit states (success, completed_no_publication, failed, skipped_due_to_active_lock)
- Timestamped report/artifact emission per run
- Configurable schedule settings
- launchd plist template for macOS
- Manual/cron documentation

### Priority 4: Omniverse Dry-Run

**E. Omniverse Adapter Bundle Path**
- Bundle builder creating structured artifact directories
- SimulationSpec serialization for external runner
- Result contract/schema for ingestion
- Dry-run mode (no Omniverse required)
- Sample result ingestion

### Priority 5: API/CLI/Docs

**F. API/CLI Extensions**
- CLI: `benchmark run`, `schedule run-once`, `omniverse build-bundle`, `omniverse ingest-result`
- API: benchmark, schedule, omniverse endpoints

**G. Documentation**
- Phase 2 plan and status docs
- Omniverse integration guide
- Benchmark guide
- Scheduler guide

## Constraints

- Do not break one-publication-per-run invariant
- Do not remove deterministic fake/mock components
- No network access required for tests
- No live Ollama or Omniverse required for tests
- Preserve backward compatibility
- Preserve auditability and rejection logging
- DB changes must be versioned, idempotent, non-destructive

## Run Modes (updated)

| Mode | Generator | Simulator | Evidence | Use Case |
|------|-----------|-----------|----------|----------|
| `deterministic_test` | Fake (fixed) | Mock | DemoFixture | Pytest, CI |
| `demo_local` | Demo (varied) | Mock | DemoFixture | Demos |
| `production_local` | Ollama | Mock | ExistingFindings | Real daily runs |
| `omniverse_stub` | Ollama | OmniverseDryRun | ExistingFindings | Omniverse prep |
| `omniverse_dry_run` | Ollama | OmniverseDryRun | ExistingFindings | Bundle generation |
