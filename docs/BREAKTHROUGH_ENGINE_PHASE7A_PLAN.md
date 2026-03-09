# Phase 7A Plan — Autonomous Operations Hardening

**Branch**: `breakthrough-engine-phase7a-autonomous-ops`
**Base**: `breakthrough-engine-phase6` @ commit `60da8f4`
**Started**: 2026-03-08

## Objective

Harden the breakthrough engine for autonomous daily discovery campaigns.
Do not add new research capabilities — focus on operational infrastructure.

## Current State

- 444 tests passing, 0 failures
- Schema v007 (36 bt_ tables)
- Phase 6 validated: Bayesian evaluation, policy optimization, daily search ladder
- Generation model: qwen3.5:9b-q4_K_M (Ollama)
- Embedding model: mock (offline-safe for tests)
- Clean-energy program configs: clean_energy.yaml, clean_energy_shadow.yaml, clean_energy_review.yaml, daily_quality.yaml

## Implementation Order

### Priority 1: Foundation
1. Schema v008 migration (campaign operations tables)
2. Strict preflight/doctor verification
3. Campaign config profiles (pilot_30m, overnight_clean_energy)

### Priority 2: Campaign Manager
4. Autonomous campaign manager with durable state
5. Campaign receipts and DB persistence

### Priority 3: Safety
6. Watchdogs, retries, fail-safe behavior
7. Lock protection for overlapping campaigns

### Priority 4: Output
8. Artifact/export hardening
9. CLI commands for campaign operations

### Priority 5: Validation
10. Comprehensive tests
11. Pilot campaign execution (30 min, clean-energy only)
12. Overnight readiness package

## Two Campaign Profiles

### pilot_30m
- Domain: clean-energy
- Wall-clock budget: 30 minutes
- Conservative thresholds
- Diagnostic-rich output
- Purpose: validate entire pipeline end-to-end

### overnight_clean_energy
- Domain: clean-energy
- Wall-clock budget: 8 hours
- Quality-first (publication threshold: 0.70)
- More exploratory sub-domain rotation
- Purpose: unattended overnight discovery

## Key Constraints
- No merge to main
- No architecture redesign
- No weakened novelty thresholds
- All tests offline-safe
- One-publication-per-run invariant preserved
- Clean-energy only for live campaigns
