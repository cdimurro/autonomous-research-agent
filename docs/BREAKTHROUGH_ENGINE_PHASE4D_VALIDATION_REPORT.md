# Phase 4D Validation Report

## Status: Implementation Validated — Live Runs Pending Ollama Availability

**Date**: 2026-03-08
**Session**: Phase 4D Last-Mile Validation

---

## Implementation Checkpoint

| Item | Value |
|------|-------|
| Tag | `breakthrough-engine-phase4d-implemented` |
| Commit | 13337ab |
| Branch | main |
| Tests | 325 passed, 0 failed, 0 warnings |
| Schema version | v005 |

---

## Phase A: Freeze Checkpoint — COMPLETE

The entire Phase 4D implementation (previously uncommitted) was committed in a single clean
commit tagged `breakthrough-engine-phase4d-implemented`. Starting state is now reproducible.

---

## Phase B: Corpus Archival Wired into Runtime — COMPLETE

**Change**: `CorpusManager.run_archival()` is now called in `_execute_cycle` before Step 2
(candidate generation).

**Rationale for pre-run hook**: Archival at the start of each run ensures the active corpus is
pruned *before* novelty comparison runs. This means the current run immediately benefits from
reduced corpus density — as opposed to a post-run hook which would only benefit the *next* run.

**What happens each run**:
1. `run_archival(domain)` archives all non-protected candidates older than `archive_age_days` (default 30)
2. Stats are logged: `archived_by_age`, `total_archived`, `active_corpus_size`
3. Stats are persisted in `bt_calibration_diagnostics.active_thresholds["corpus_maintenance"]`
4. Archival is non-fatal: any exception logs a warning and the run continues

**Protected statuses** (never archived): `published`, `draft_pending_review`

**New tests**: 4 tests covering archival wiring, age-based archival, protected status invariant,
and calibration diagnostic persistence.

---

## Phase C: Active-Corpus Novelty Filtering Wired — COMPLETE

**Change**: `_run_novelty_gate` now filters `prior_texts` (the embedding comparison corpus) to
active (non-archived) candidates only.

**Before**: All prior candidates for the domain were compared against.
**After**: Only `get_active_candidate_ids(domain)` members are compared against.

**Scope policy**: `active_only` (default). Archived candidates are excluded from embedding
comparison. Retrieved evidence papers are still included (unchanged).

**Logged per run**:
```
[<run_id>] Novelty corpus: total_prior=120 active=90 (archived excluded=30)
```

**New tests**: 4 tests covering active-id exclusion, empty-active-corpus run, and
same-domain duplicate blocking still works correctly with active corpus.

---

## Phase D: Live Validation — BLOCKED

**Reason**: Ollama not reachable in this environment.

```
curl http://localhost:11434/api/tags → exit code 7 (connection refused)
ollama binary: not in PATH
```

**All code wiring is complete and tested offline.** Live validation requires an operator
to run the following commands in an environment with Ollama available:

```bash
# 1. Bootstrap findings (first time only)
.venv/bin/python -m breakthrough_engine.bootstrap_findings --domain all

# 2. Verify Ollama models are available
ollama list | grep -E "qwen|nomic"

# 3. Clean-energy validation (4 shadow + 2 review)
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain clean-energy --mode production_shadow --runs 4
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain clean-energy --mode production_review --runs 2

# 4. Materials science validation (4 shadow + 2 review)
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain materials-science --mode production_shadow --runs 4
.venv/bin/python scripts/phase4c_live_validation.py \
  --domain materials-science --mode production_review --runs 2
```

**What to record for each run**:
- run_id, domain, sub_domain from bt_diversity_context
- mode, candidates generated, blocked (embedding), warned
- active_corpus_size from calibration diagnostic
- archived_this_run from calibration diagnostic
- draft created (yes/no)

**Key comparison to make**:

| Metric | Phase 4C Baseline | Phase 4D Expected |
|--------|-------------------|-------------------|
| Embedding block rate | 90% (35/39) | Target: 30-60% |
| Max similarity avg | 0.950 | Target: <0.92 |
| Sub-domain spread | Single cluster | 10 rotating sub-domains |
| Negative memory | None | Top 10 excluded topics per run |
| Active corpus size | 120 (all) | Decreasing via archival |

---

## Phase E: Diversity / Saturation Analysis — DEFERRED

Pending live run data. Framework:

**Questions to answer with real data**:
1. Did embedding block rate fall materially from 90%?
2. Did materials behave differently from clean-energy (lower saturation)?
3. Did sub-domain rotation increase sub-domain spread across 8 runs?
4. Did negative memory reduce repeated nearest-neighbor titles?
5. Did active-corpus filtering change block behavior (archived = fewer comparisons)?
6. Are more runs resulting in drafts?

---

## Phase F: Minimal Fixes — DEFERRED

No evidence-based fixes applied without live data. Will revisit after live runs.

---

## Phase G: Final Testing — COMPLETE

```
325 passed in 6.76s (0 failed, 0 warnings)
```

Full suite run after all Phase B+C changes and new tests. All existing tests preserved.
New test count: +8 (runtime archival wiring: 4, active-corpus filtering: 4).

---

## Phase H: Baseline Commit and Tag

| Tag | Commit | Status |
|-----|--------|--------|
| `breakthrough-engine-phase4d-implemented` | 13337ab | CREATED |
| `breakthrough-engine-phase4d-validated` | TBD | PENDING live runs |

---

## Summary Table

| Phase | Task | Status |
|-------|------|--------|
| A | Freeze implementation checkpoint | COMPLETE |
| B | Wire corpus archival into runtime | COMPLETE |
| C | Wire active-corpus novelty filtering | COMPLETE |
| D | Live validation (8 shadow + 4 review cycles) | BLOCKED (no Ollama) |
| E | Diversity/saturation analysis | DEFERRED |
| F | Minimal fixes if justified | DEFERRED |
| G | Final test suite | COMPLETE (325 passed) |
| H | Validated baseline tag | DEFERRED |

---

## Recommended Next Step

**Phase 4D Live Validation Pass** — requires Ollama with `nomic-embed-text` and a generation
model (e.g., `qwen3.5:9b-q4_K_M`). Run the 8+4 cycle plan above, record block rates,
and compare against the 90% Phase 4C baseline. If block rate is materially lower (< 70%),
tag `breakthrough-engine-phase4d-validated` and recommend starting Phase 5.

If block rate is still high after diversity steering, the most likely causes are:
1. Active corpus is still dense (archival not yet meaningful for recent DB)
2. Sub-domain rotation needs more runs to show effect
3. Negative memory window may need tuning (currently last 10 blocked titles)

No threshold changes should be made without this evidence.
