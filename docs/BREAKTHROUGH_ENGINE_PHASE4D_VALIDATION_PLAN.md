# Phase 4D Validation Plan

## Objective

Convert Phase 4D from "implementation complete" to "validated and baseline-ready."

## Captured State at Session Start (2026-03-08)

| Item | Value |
|------|-------|
| Branch | main |
| Commit hash | fd53b7f94fb82951c6f7413a9d20de909af9be90 |
| Schema version | v005 |
| Test count | 317 passing, 0 failures, 0 warnings |
| clean-energy candidates in DB | 120 |
| materials-science candidates in DB | 4 (bootstrap only, no prior runs) |
| cross-domain candidates | 8 |
| bt_diversity_context rows | 0 (no Phase 4D runs yet) |
| bt_rotation_state rows | 0 |
| bt_corpus_archive rows | 0 |
| Novelty thresholds | embedding_block=0.88, embedding_warn=0.78 |
| Phase 4C baseline block rate | 90% (35/39 candidates blocked) |

## Ollama Availability Check

```
curl http://localhost:11434/api/tags → EXIT:7 (connection refused)
ollama binary: not found in PATH
```

**Result: Ollama is UNAVAILABLE in this environment.**

Live validation with real generation/embedding models is blocked. All validation
will use the offline test harnesses, which use FakeCandidateGenerator and MockEmbeddingProvider.
This is documented honestly as a constraint and does not block the code wiring tasks.

## Phases

### Phase A: Freeze Implementation Checkpoint
- Verify Phase 4D implementation state
- Run full test suite
- Commit all Phase 4D work
- Tag as `breakthrough-engine-phase4d-implemented`

### Phase B: Wire Corpus Archival into Runtime
- Add `CorpusManager.run_archival()` call to `_execute_cycle` pre-generation step
- Log archival stats per run
- Expose stats in calibration diagnostic
- Add targeted tests

### Phase C: Wire Active-Corpus Filtering into Novelty
- Filter `prior_texts` in `_run_novelty_gate` to active candidates only
- Log active vs total corpus sizes
- Add targeted tests

### Phase D: Live Validation
- **BLOCKED**: Ollama not available in current environment
- Document exact commands for operator to run when Ollama is available
- Expected run plan: 4 production_shadow + 2 production_review per domain

### Phase E: Diversity / Saturation Analysis
- Deferred pending live runs
- Framework documented for operator to complete

### Phase F: Minimal Fixes
- No fixes applied without live evidence

### Phase G: Final Testing
- Full suite pass required before tag

### Phase H: Final Baseline Commit and Tag
- If validation complete: `breakthrough-engine-phase4d-validated`
- If Ollama blocked: `breakthrough-engine-phase4d-implemented` checkpoint only
- Operator runs live validation when Ollama available

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| 317 tests passing | DONE |
| Implementation checkpoint committed | PENDING Phase A |
| Archival wired into runtime | PENDING Phase B |
| Active-corpus novelty filtering wired | PENDING Phase C |
| Live validation runs (4+4 shadow, 2+2 review) | BLOCKED (no Ollama) |
| Final validated baseline tag | BLOCKED (depends on live runs) |
