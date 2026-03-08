# Breakthrough Engine - Calibration Report

**Date:** 2026-03-08
**Baseline commit:** `a371223` on `main`
**Post-calibration tests:** 176 passed, 0 warnings

---

## 1. Operational Readiness Assessment

### Is the system ready for regular production_shadow runs?
**PARTIALLY.** The pipeline handles production_shadow gracefully even when Ollama is unavailable (returns completed_no_publication with 0 candidates, no crash). However, without a running Ollama instance and populated scires.db, production_shadow produces no useful output. The pipeline mechanics are sound; the dependency on external services is the bottleneck.

### Is it ready for production_review runs?
**PARTIALLY.** Same situation as production_shadow — the review workflow code is tested and works (verified via unit tests and the demo_local pipeline), but cannot produce drafts without Ollama.

### How often did it produce genuinely interesting candidates?
In demo_local mode, **3 out of 4 runs produced a publication** (runs 2-4). Run 5 correctly saturated after all 4 demo candidates were consumed. The demo candidates are hardcoded and scientifically plausible (perovskite solar cells, MOF-CRISPR diagnostics, neuromorphic carbon capture) but are not generated from real evidence. Real quality assessment requires Ollama-generated candidates.

### How often would a human reviewer likely approve a draft?
With demo candidates: **high approval rate** (all scored >0.85). This reflects the quality of the hand-crafted demo fixtures, not real LLM generation quality. Real approval rates are unknown until Ollama calibration is possible.

### Top 3 real bottlenecks
1. **Ollama not available** — blocks all production_shadow and production_review testing
2. **Demo generator is domain-agnostic** — produces the same 4 candidates for every domain, leading to domain mismatch (clean_energy publishes CRISPR, materials publishes carbon capture)
3. **No scires.db / findings** — ExistingFindingsSource has no data, so real evidence retrieval is untestable

---

## 2. Calibration Run Scorecards

### Run 2: general_fast_loop (demo_local) — "Perovskite-TI Solar Cell"

| Dimension | Score | Notes |
|-----------|-------|-------|
| Novelty quality | 4 | Novel cross-domain combination (perovskite + topological insulator) |
| Plausibility | 4 | Physically reasonable, mechanism is stated |
| Evidence quality | 3 | Two evidence items, both relevant but pre-selected fixtures |
| Simulation usefulness | 2 | Mock simulator — adds no real signal |
| Publication worthiness | 3 | Interesting idea but not grounded in real retrieval |
| Operator review burden | 5 | Clear, short, easy to review |
| Overall signal quality | 3 | Decent pipeline demo, but demo-generated |

### Run 3: clean_energy (demo_local) — "MOF-Enhanced CRISPR Diagnostic Platform"

| Dimension | Score | Notes |
|-----------|-------|-------|
| Novelty quality | 3 | Interesting but not clean-energy related |
| Plausibility | 3 | MOF + CRISPR combination is plausible in biodiagnostics |
| Evidence quality | 2 | Evidence items don't match the clean-energy domain |
| Simulation usefulness | 2 | Mock simulator |
| Publication worthiness | 2 | Domain mismatch — clean-energy program publishing CRISPR |
| Operator review burden | 5 | Easy to review |
| Overall signal quality | 2 | Domain-mismatch artifact of demo generator |

### Run 4: materials (demo_local) — "Neuromorphic Carbon Capture Controller"

| Dimension | Score | Notes |
|-----------|-------|-------|
| Novelty quality | 4 | Genuine cross-domain novelty (SNN + MOF control) |
| Plausibility | 3 | Reasonable but SNN process control is immature |
| Evidence quality | 3 | Two relevant evidence items |
| Simulation usefulness | 2 | Mock simulator |
| Publication worthiness | 3 | Interesting concept, better domain fit |
| Operator review burden | 5 | Easy to review |
| Overall signal quality | 3 | Better domain alignment than run 3 |

### Aggregate Summary

| Metric | Value |
|--------|-------|
| Total runs scored | 3 (demo_local with publications) |
| Average overall signal quality | 2.7 / 5 |
| Runs with genuinely interesting output | 2 of 3 |
| Runs where draft would deserve human review | 1 of 3 (run 2) |
| Most common failure mode | Domain mismatch (demo generator ignores domain) |

---

## 3. Failure Pattern Analysis

### Bucket 1: No candidates generated (production_shadow/review)
- **Frequency:** 2/6 runs (all production_shadow/review attempts)
- **Severity:** High — blocks all useful output
- **Root cause:** Ollama not running, no scires.db
- **Fix scope:** Environment setup (not a code fix)
- **Belongs to:** Pre-Phase-4 setup requirement

### Bucket 2: Domain mismatch in demo candidates
- **Frequency:** 2/3 demo_local publications
- **Severity:** Medium — misleading but harmless in demo mode
- **Root cause:** DemoCandidateGenerator returns fixed candidates regardless of domain
- **Fix scope:** Could improve demo generator, but low priority (demo mode is for testing mechanics)
- **Belongs to:** Not blocking; acceptable for demo mode

### Bucket 3: Novelty saturation with fixed candidates
- **Frequency:** 1/6 runs (run 5)
- **Severity:** Low — expected and correct behavior
- **Root cause:** Only 4 unique demo candidates exist; dedup correctly rejects known ones
- **Fix scope:** Not a bug — demonstrates dedup working correctly
- **Belongs to:** N/A

### Bucket 4: Evidence harness consistent rejection
- **Frequency:** "Cross-Domain Synthesis: Novel Perovskite" rejected in all 3 demo runs
- **Severity:** Low — correct behavior (only has 1 evidence item, threshold is 2)
- **Root cause:** Demo evidence mapping assigns only 1 item to this candidate
- **Fix scope:** Not a bug
- **Belongs to:** N/A

### Bucket 5: Mock simulation adds no signal
- **Frequency:** All runs
- **Severity:** Medium — simulation_readiness score is always high, inflating final scores
- **Root cause:** MockSimulatorAdapter always returns "completed" with synthetic metrics
- **Fix scope:** Phase 4C (live Omniverse) or could add variance to mock
- **Belongs to:** Phase 4

### Bucket 6: Warning noise (FIXED)
- **Frequency:** Was 693 warnings per test run
- **Severity:** High — obscured real test output
- **Root cause:** `datetime.utcnow()` deprecation in Python 3.12+
- **Fix applied:** Replaced all 14 call sites with timezone-aware equivalent
- **Result:** 0 warnings

---

## 4. Calibration Fix Applied

### Fix: datetime.utcnow() deprecation warnings

- **Observed issue:** 693 DeprecationWarnings per test run from `datetime.utcnow()` usage
- **Files changed:** 7 files (models.py, orchestrator.py, db.py, simulator.py, notifications.py, reporting.py, evidence_source.py)
- **Change:** Replaced `datetime.utcnow()` with `datetime.now(timezone.utc).replace(tzinfo=None)` to maintain naive datetime behavior while eliminating the warning
- **Added:** `_utcnow()` helper function in models.py for Pydantic `default_factory` usage
- **Test result:** 176 passed, 0 warnings in 0.31s
- **Risk:** Minimal — exact same runtime behavior, just uses non-deprecated API

---

## 5. Phase 4 Recommendation

### Evidence-based assessment

The calibration reveals that the **pipeline mechanics are solid** — all gates, harnesses, scoring, dedup, novelty, reporting, and lifecycle management work correctly. The system handles missing dependencies gracefully.

The **primary operational gap** is the lack of real candidate generation. Without Ollama, the system cannot produce novel, domain-specific hypotheses. Without scires.db findings, it cannot retrieve real evidence. These are the two dependencies that would unlock meaningful daily runs.

### Recommended Phase 4 target: **Phase 4A — Retrieval Quality + Candidate Generation Bootstrapping**

**Rationale:**
1. Both production_shadow and production_review are blocked on Ollama + real evidence, not on pipeline logic
2. The demo generator's domain-agnostic behavior shows that real LLM generation with domain-aware prompting is the highest-value gap
3. Retrieval (OpenAlex/Crossref) is implemented but untested with live data — this is the second-highest gap
4. Embedding-based novelty (Phase 4B) is premature — lexical novelty works correctly; the bottleneck is generation quality, not novelty detection
5. Omniverse execution (Phase 4C) adds no value until candidate quality is high enough to warrant simulation
6. A dashboard (Phase 4D) adds no value until there are real runs producing real data to display

### Phase 4A scope
1. Stand up Ollama with a suitable model (llama3:8b or better)
2. Populate scires.db with real paper findings from at least one domain
3. Run 10+ production_shadow cycles with real candidates
4. Tune Ollama prompt for domain-specific, well-structured hypothesis generation
5. Enable live OpenAlex/Crossref retrieval with rate limiting
6. Run 10+ production_review cycles and evaluate draft quality
7. Iterate on publication threshold and novelty threshold based on real data

### Alternative if Ollama is not available
If local Ollama setup is not feasible, consider:
- Adding an API-based LLM backend (e.g., Claude API via `anthropic` SDK)
- Pre-seeding scires.db with a sample findings dataset for testing

---

## 6. Summary

| Area | Status |
|------|--------|
| Baseline verified | 176 tests pass, commit a371223 |
| Warnings fixed | 693 → 0 |
| Live runs completed | 6 (3 demo_local with publications, 1 demo_local saturated, 1 production_shadow empty, 1 production_review empty) |
| Pipeline mechanics | Fully operational |
| Real candidate generation | BLOCKED (no Ollama) |
| Real evidence retrieval | BLOCKED (no scires.db, no network tested) |
| Review workflow | Tested via unit tests, not via live drafts |
| Code changes | datetime fix only (7 files, minimal risk) |
| Recommended Phase 4 | **4A: Retrieval Quality + Candidate Generation Bootstrapping** |
