# Phase 4D Validation Status

## Current Status: Wiring Complete — Live Validation Blocked (Ollama Unavailable)

## Session: 2026-03-08

### Phase A: Implementation Checkpoint — COMPLETE

| Item | Value |
|------|-------|
| Commit hash (implementation) | breakthrough-engine-phase4d-implemented |
| Tests at checkpoint | 317 passed, 0 failed |
| Schema version | v005 |
| All Phase 4D files | committed |

### Phase B: Corpus Archival Wiring — COMPLETE

- `CorpusManager.run_archival()` now called at the start of `_execute_cycle` (before candidate generation)
- Rationale: pre-run archival ensures active corpus is pruned *before* novelty comparison runs,
  so this run benefits immediately from the maintained corpus
- Stats logged per run: domain, archived_by_age, total_archived, active_corpus_size
- Stats included in calibration diagnostic under `corpus_maintenance` key
- Archival is non-fatal: failure is logged as warning, run continues normally

### Phase C: Active-Corpus Novelty Filtering — COMPLETE

- `_run_novelty_gate` now filters prior candidates to active (non-archived) only
- Prior corpus size (before filter) and active corpus size (after filter) are both logged
- `prior_texts` list for embedding comparison is now built only from active candidates
- Same-domain duplicate blocking preserved correctly (only archived candidates excluded)
- Scope policy is `active_only` by default (archived candidates not compared)

### Phase D: Live Validation — BLOCKED

**Reason**: Ollama not reachable (`curl http://localhost:11434/api/tags` → connection refused)

**Commands to run when Ollama is available:**

```bash
# Bootstrap materials findings (if not yet done)
.venv/bin/python -m breakthrough_engine.bootstrap_findings --domain all

# Phase 4D clean-energy validation (4 shadow + 2 review)
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain clean-energy --mode production_shadow --runs 4
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain clean-energy --mode production_review --runs 2

# Phase 4D materials validation (4 shadow + 2 review)
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain materials-science --mode production_shadow --runs 4
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain materials-science --mode production_review --runs 2
```

**What to record for each run** (see validation plan for full checklist):
- run_id, domain, sub_domain, mode, embedding_block_rate, active_corpus_size, draft_outcome

### Phase E–F: Analysis and Fixes — DEFERRED

Pending live run data.

### Phase G: Final Tests — COMPLETE (pre-live)

```
317 passed in 6.78s (after Phase B+C wiring)
```

Full suite passes with new archival and active-corpus filtering wired in.

### Phase H: Baseline Commit — PARTIAL

- Implementation checkpoint: `breakthrough-engine-phase4d-implemented`
- Validated baseline tag: DEFERRED (requires live runs)

## Remaining Gap

Only one gap remains before validated baseline can be declared:

> **Run live Ollama validation (8 shadow + 4 review cycles across two domains) and compare
> embedding block rate against Phase 4C baseline (90%).**

All code wiring is complete. The architecture is ready for live validation.
