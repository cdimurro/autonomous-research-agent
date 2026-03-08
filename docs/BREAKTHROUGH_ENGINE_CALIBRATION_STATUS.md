# Breakthrough Engine - Calibration Status

**Status: Calibration Complete**

## Baseline

- **Commit:** `a371223` on branch `main`
- **Working tree:** All breakthrough files untracked (never committed — all added in Phases 1-3)
- **Schema version:** v002 (v001 initial + v002 Phase 3 tables)
- **Python:** 3.14.3 with venv at `.venv/`

## Baseline Test Results

```
Command: .venv/bin/python -m pytest tests/test_breakthrough/ -v
Result: 176 passed, 693 warnings in 0.36s
```

All 693 warnings were `datetime.datetime.utcnow()` deprecation warnings from 8 model fields + 6 code call sites.

## Runtime Readiness Summary

| Dependency | Status | Details |
|-----------|--------|---------|
| Ollama | **BLOCKED** | Not running on localhost:11434 |
| scires.db | **BLOCKED** | File does not exist |
| Research programs | **PASS** | 3 programs: general_fast_loop, clean_energy, materials |
| Demo fixtures | **PASS** | DemoFixtureSource returns 6 evidence items |
| Demo generator | **PASS** | DemoCandidateGenerator returns 4 candidates |
| Mock simulator | **PASS** | Deterministic, always available |
| SQLite DB init | **PASS** | Creates runtime/db/scires.db on first run |
| Notifications | **PASS** | LoggingNotifier works |
| Retrieval cache | **PASS** | SQLite-backed, works with in-memory DB |
| production_shadow | **BLOCKED** | Requires Ollama + scires.db findings |
| production_review | **BLOCKED** | Requires Ollama + scires.db findings |
| demo_local | **PASS** | Fully functional |
| deterministic_test | **PASS** | Fully functional |

## Calibration Runs Completed

### Run 1: production_shadow (general_fast_loop)
- **Run ID:** `48ee3b774d1041fb`
- **Mode:** production_shadow
- **Duration:** 6.05s (Ollama retry timeout)
- **Candidates:** 0 generated (Ollama unreachable)
- **Evidence:** 0 (no findings table)
- **Result:** completed_no_publication
- **Observation:** Graceful degradation — no crash, proper status

### Run 2: demo_local (general_fast_loop)
- **Run ID:** `133cf7531d894ebd`
- **Mode:** demo_local
- **Duration:** <0.01s
- **Candidates:** 4 generated, 1 published, 3 rejected
- **Published:** "Perovskite-Topological Insulator Hybrid Solar Cell" (score=0.883)
- **Rejections:** 1 evidence_failed (insufficient count), 0 novelty (first run)

### Run 3: demo_local (clean_energy)
- **Run ID:** `aef3accc62cb447d`
- **Mode:** demo_local
- **Duration:** <0.01s
- **Candidates:** 4 generated, 1 published, 3 rejected
- **Published:** "MOF-Enhanced CRISPR Diagnostic Platform" (score=0.891)
- **Rejections:** 1 evidence_failed, 1 novelty_failed (Perovskite-TI from run 2)
- **Observation:** Domain mismatch — clean_energy program published CRISPR candidate

### Run 4: demo_local (materials)
- **Run ID:** `319fa3e674ba4841`
- **Mode:** demo_local
- **Duration:** <0.01s
- **Candidates:** 4 generated, 1 published, 3 rejected
- **Published:** "Neuromorphic Carbon Capture Controller" (score=0.851)
- **Rejections:** 1 evidence_failed, 2 novelty_failed

### Run 5: demo_local (general_fast_loop — novelty saturation)
- **Run ID:** `45ce1ccf8428...`
- **Mode:** demo_local
- **Duration:** <0.01s
- **Candidates:** 4 generated, 0 published, 4 rejected
- **Rejections:** All 4 dedup_rejected (similarity=1.00)
- **Observation:** Novelty saturation — all demo candidates now known

### Run 6: production_review (general_fast_loop)
- **Run ID:** (auto-generated)
- **Mode:** production_review
- **Duration:** ~6s (Ollama retry timeout)
- **Candidates:** 0 generated (Ollama unreachable)
- **Drafts:** 0 created
- **Result:** completed_no_publication

## Warning Summary

### Before fix
- 693 total warnings
- **Source:** `datetime.datetime.utcnow()` deprecation (Python 3.12+)
- **Locations:** 8 model field defaults + 6 code call sites across 6 files

### After fix
- **0 warnings**
- Fix: Replaced all `datetime.utcnow()` with `datetime.now(timezone.utc).replace(tzinfo=None)`
- Added `_utcnow()` helper in models.py for default_factory usage
- Preserves naive datetime behavior (no timezone-aware change)

## Files Changed (Calibration)

| File | Change | Justification |
|------|--------|---------------|
| `breakthrough_engine/models.py` | Added `_utcnow()` helper, replaced 8 `default_factory=datetime.utcnow` | Fix 693 deprecation warnings |
| `breakthrough_engine/orchestrator.py` | `datetime.utcnow()` → `datetime.now(timezone.utc).replace(tzinfo=None)` (2 sites) | Same |
| `breakthrough_engine/db.py` | Same replacement (2 sites) | Same |
| `breakthrough_engine/simulator.py` | Same replacement (1 site) | Same |
| `breakthrough_engine/notifications.py` | Same replacement (1 site) | Same |
| `breakthrough_engine/reporting.py` | Same replacement (1 site) | Same |
| `breakthrough_engine/evidence_source.py` | Same replacement (1 site) | Same |

## Post-Fix Test Results

```
Command: .venv/bin/python -m pytest tests/test_breakthrough/ -v
Result: 176 passed, 0 warnings in 0.31s
```

## Blockers

1. **Ollama not running:** Cannot test production_shadow or production_review with real LLM candidates
2. **No scires.db:** ExistingFindingsSource has no data to retrieve

## Known Limitations

1. Demo generator produces fixed 4 candidates regardless of domain or evidence
2. Demo evidence fixtures are domain-agnostic (clean_energy publishes CRISPR candidate)
3. After 3 demo_local runs, all demo candidates are consumed by novelty dedup
4. production_shadow/review modes require external services not available in this environment
5. No real retrieval testing possible without network access

## Next Recommended Step

Start Ollama with a suitable model (e.g., `llama3:8b`) and populate scires.db with findings to enable real production_shadow calibration. See Phase 4 recommendation in the calibration report.
