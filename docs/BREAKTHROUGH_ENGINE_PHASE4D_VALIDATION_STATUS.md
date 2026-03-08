# Phase 4D Validation Status

## Current Status: VALIDATED — All Runs Complete, Baseline Tagged

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

### Live Validation Results — COMPLETE

| Domain | Runs | Block Rate | Avg Max Sim | Drafts |
|--------|------|------------|-------------|--------|
| clean-energy | 6 | 0% | 0.636 | 2/2 review |
| materials-science | 6 | 0% | 0.600 | 2/2 review |
| **Phase 4C baseline** | 8 | **90%** | **0.950** | 2/3 review |

Block rate: **90% → 0%**. Avg max similarity: **0.950 → 0.618**. All thresholds unchanged.

### Phase E: Analysis — COMPLETE

See [BREAKTHROUGH_ENGINE_PHASE4D_VALIDATION_REPORT.md](BREAKTHROUGH_ENGINE_PHASE4D_VALIDATION_REPORT.md).

### Phase F: Fixes Applied

- SQL update: added `materials-science` to materials paper subjects (hyphen mismatch)
- Added `materials_shadow.yaml` and `materials_review.yaml` program configs

### Phase G: Final Tests — COMPLETE

```
325 passed in 6.76s (0 failed, 0 warnings)
```

### Phase H: Baseline Tags — COMPLETE

- Implementation: `breakthrough-engine-phase4d-implemented`
- Validated: `breakthrough-engine-phase4d-validated`
