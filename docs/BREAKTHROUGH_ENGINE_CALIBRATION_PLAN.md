# Breakthrough Engine - Calibration Plan

## Purpose

Post-Phase-3 operational calibration: verify the system works end-to-end on real local runs before starting Phase 4.

## Scope

- Freeze the Phase 3 baseline
- Verify local runtime readiness
- Run real end-to-end cycles in safe modes
- Inspect outputs and build a calibration scorecard
- Identify failure modes from observed behavior
- Apply only minimal, justified fixes
- Produce a final calibration report with a recommended Phase 4 target

## Constraints

- No new architecture or subsystems
- No speculative refactors
- Every code change must map to an observed calibration issue
- Do not auto-publish or auto-approve drafts
- Preserve deterministic test/demo modes
- No network-dependent tests

## Phases

### Phase A: Freeze and Verify Baseline
- Record commit hash, branch, dirty state
- Run full test suite, record results
- Audit and classify warnings

### Phase B: Local Runtime Readiness Check
- Check Ollama availability
- Check scires.db existence and content
- Validate config for all run modes
- Produce readiness summary (PASS / PARTIAL / BLOCKED)

### Phase C: Safe Live Calibration Runs
- Run up to 10 production_shadow cycles
- Run up to 3 demo_local cycles per program
- Run up to 3 production_review cycles
- Capture run metrics, candidate counts, rejection reasons

### Phase D: Output Inspection and Scorecard
- Score each run on 7 dimensions (1-5 scale)
- Record qualitative observations
- Compute aggregate summary

### Phase E: Failure Pattern Analysis
- Classify failures into buckets
- Record frequency, severity, root cause
- Assign fix scope (calibration vs Phase 4)

### Phase F: Minimal Calibration Fixes
- Only fixes justified by observed issues
- Rerun tests after each fix

### Phase G: Production_review Validation
- Run production_review cycles
- Inspect draft creation behavior
- Do not auto-approve

### Phase H: Warning Reduction
- Audit warning categories
- Fix repo-owned warning sources
- Record new warning count

### Phase I: Final Calibration Report
- Operational readiness assessment
- Recommended Phase 4 target based on evidence
