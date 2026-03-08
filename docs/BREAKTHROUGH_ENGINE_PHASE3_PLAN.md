# Breakthrough Engine - Phase 3 Plan: Live Discovery Readiness

## Objective

Move the engine from "good local prototype" to "live discovery workflow with retrieval, novelty checks, and operator review safety."

## Baseline (Phase 2 state at start of Phase 3)

- 17 Python modules in `breakthrough_engine/`
- 124 passing tests, 0 failing
- 12 `bt_`-prefixed SQLite tables, schema version 1
- OllamaCandidateGenerator, ExistingFindingsSource, FutureRetrievalSource (stub)
- Benchmark suite (9/9), scheduler with locking, Omniverse dry-run
- Run modes: deterministic_test, demo_local, production_local, omniverse_stub, omniverse_dry_run
- Auto-publish on all modes (no review gate)

## Phase 3 Deliverables

### Priority 1: External Retrieval + Caching

**A. External Retrieval Sources**
- OpenAlexRetrievalSource (free API, no key required)
- CrossrefRetrievalSource (free API)
- Query construction from program domain + keywords
- Recency / max result / source-specific parsing
- Normalize to EvidenceItem model
- Local SQLite cache layer to avoid hammering APIs
- Timeout / retry / backoff
- All tests mock HTTP — no live internet required

### Priority 2: Novelty Engine

**B. Novelty / Prior-Art Analysis**
- New module: `novelty.py`
- NoveltyResult model: candidate_id, novelty_score, duplicate_risk_score, prior_art_hits, overlap_reasons, decision, explanation
- Layered heuristic analysis: exact match, token overlap, mechanism overlap, keyword overlap, similarity against past candidates, similarity against retrieved papers
- Novelty gate in orchestrator pipeline (between evidence gate and scoring)
- New candidate status: NOVELTY_FAILED
- Persistence in bt_novelty_checks table
- Explainable output in reports

### Priority 3: Operator Review Workflow

**C. Review-Based Publication**
- Publication draft lifecycle: draft_pending_review → draft_approved / draft_rejected → published
- New tables: bt_publication_drafts, bt_review_events
- production_review mode: creates draft instead of auto-publishing
- CLI: review list, review show, review approve, review reject
- API: /review/queue, /review/drafts/<id>, approve/reject endpoints
- One-publication-per-run invariant preserved
- demo_local and deterministic_test still auto-publish

### Priority 4: Live Run Modes + Metrics

**D. Run Modes**
- Add: PRODUCTION_REVIEW, PRODUCTION_SHADOW
- production_review: full pipeline, creates draft, requires approval
- production_shadow: full pipeline, no publication/draft, metrics only
- Scheduler defaults to production_review for safety
- Existing modes unchanged

**E. Metrics / Observability / Notifications**
- Per-run metrics: stage durations, candidate counts by state, novelty failures, draft status
- bt_run_metrics table
- Metrics in reports and API
- Pluggable notifiers: logging, file, webhook interface
- Notifications: run completed, draft awaiting review, run failed

### Priority 5: API / CLI / Docs / Tests

**F. API + CLI**
- CLI: run --mode production_review/shadow, review commands, metrics recent, retrieval test
- API: review routes, metrics routes, novelty route, retrieval test route
- Minimal operator HTML views for review queue

**G. Schema Migration v002**
- bt_publication_drafts, bt_review_events, bt_novelty_checks, bt_run_metrics, bt_retrieval_cache
- Versioned, idempotent, non-destructive

**H. Tests**
- External retrieval (mocked HTTP)
- Cache behavior
- Novelty engine (duplicate, overlap, novel)
- Review workflow (draft → approve → publish, draft → reject)
- Run mode behavior (production_review, production_shadow)
- Metrics persistence
- Notification hooks (mocked)
- API smoke tests
- Preserve all 124 existing tests

## Constraints

- Do not break one-publication-per-run invariant
- Do not remove deterministic fake/mock components
- No live external APIs for tests
- No live Ollama/Omniverse for tests
- Backward compatible
- Production defaults favor safety (review mode)
- Novelty scoring must be explainable

## Run Modes (updated for Phase 3)

| Mode | Generator | Simulator | Evidence | Review | Use Case |
|------|-----------|-----------|----------|--------|----------|
| `deterministic_test` | Fake | Mock | DemoFixture | Auto-publish | Pytest, CI |
| `demo_local` | Demo | Mock | DemoFixture | Auto-publish | Demos |
| `production_local` | Ollama | Mock | ExistingFindings | Auto-publish | Legacy local runs |
| `production_review` | Ollama | Mock | External+Local | Draft→Review | Safe production |
| `production_shadow` | Ollama | Mock | External+Local | No publish | Observation only |
| `omniverse_stub` | Ollama | OmniverseStub | ExistingFindings | Auto-publish | Integration prep |
| `omniverse_dry_run` | Ollama | OmniverseDryRun | ExistingFindings | Auto-publish | Bundle generation |
