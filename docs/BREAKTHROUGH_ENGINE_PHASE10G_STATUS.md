# Phase 10G: Limited Production Retrieval A/B — Status

**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Date:** 2026-03-13

## Deliverable Status

| Deliverable | Status |
|-------------|--------|
| A: Experiment branch + comparability lock | COMPLETE |
| B: Production safety guardrails | COMPLETE |
| C: Limited A/B execution (6+6) | COMPLETE |
| D: Review label collection | COMPLETE (24 labels) |
| E: Comparison summary | COMPLETE |
| F: Switch decision | COMPLETE (`continue_limited_ab`) |
| G: Rollback/reversion readiness | COMPLETE |
| H: Testing | COMPLETE (1142 passing) |
| I: Artifact packaging | COMPLETE |
| J: Commit | PENDING |

## Key Results

- **Score**: Graph-native 0.9079 vs Current 0.9042 (+0.004)
- **Approval**: Both 100%
- **Diversity check**: FAIL (in-pipeline evidence pack diversity lower for graph-native)
- **Recommendation**: `continue_limited_ab`
- **Tests**: 1142 passing, 0 failures
- **Production default**: Unchanged, verified by tests

## Blocker Fix

The initial A/B script failed to extract run_ids from DailyCampaignResult.ladder_stages
(LadderStageResult has no run_id field). Backfilled from bt_daily_campaigns table
using champion_candidate_id -> bt_candidates.run_id. All 12 campaigns had valid
data in the DB; only the script's extraction logic was broken.
