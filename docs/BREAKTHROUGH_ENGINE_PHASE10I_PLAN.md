# Phase 10I: Diversity-Aware Evidence Ranking, Persistence Repair, Confirmatory A/B

**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Date:** 2026-03-14

## Objective

Fix the two specific bottlenecks preventing graph-native retrieval from clearing
the final promotion gate:

1. **Ranking-layer diversity collapse**: `rank_evidence()` selects top-k by
   composite score alone, concentrating evidence packs on one source paper.
2. **Evidence item persistence bug**: `INSERT OR REPLACE` collisions cause
   only the last pack to retain its evidence items.

Then rerun a confirmatory 7+7 limited A/B under the same locked conditions.

## Fixes

### A. Diversity-Aware Ranking (`select_diverse_top_k`)

- New function in `retrieval.py` that wraps `rank_evidence()` output
- Per-source cap (default: 1 item per source_id in top-k)
- Diversity penalty for repeated sources
- Bypass for exceptionally strong items (margin >= 0.15 over best other source)
- Relaxation fallback when caps prevent filling k
- Called from `orchestrator.py:_run_evidence_gate()` replacing naive `ranked[:k]`

### B. Evidence Item Persistence Repair

- Root cause: all candidates in a run share the same `EvidenceItem` objects
  with identical IDs. `save_evidence_pack()` uses `INSERT OR REPLACE` by item ID,
  so when pack N saves item A, it overwrites pack N-1's reference.
- Fix: create fresh `EvidenceItem` copies with `new_id()` for each pack
- Applied in `orchestrator.py:_run_evidence_gate()` before `EvidencePack` creation

### C. Confirmatory A/B

- 7+7 campaigns, same conditions as Phase 10H
- Both arms use the ranking and persistence fixes
- Expanded metrics: persistence rate, packs_with_items, total_packs

## Constraints

- Do not merge to main
- Do not switch production retrieval
- Policy: evidence_diversity_v1 (fixed)
- Embedding: qwen3-embedding:4b (fixed)
- Generation: qwen3.5:9b-q4_K_M (fixed)
- All tests offline-safe
- One-publication-per-run invariant preserved

## Deliverables

| ID | Deliverable | Status |
|----|-------------|--------|
| A | Ranking-layer diagnosis | COMPLETE |
| B | Diversity-aware ranking | COMPLETE |
| C | Evidence persistence repair | COMPLETE |
| D | Comparability re-check | COMPLETE |
| E | Confirmatory A/B (7+7) | COMPLETE |
| F | Review label collection | COMPLETE (28 labels) |
| G | Final comparison summary | COMPLETE |
| H | Switch decision | COMPLETE (`continue_limited_ab`) |
| I | Rollback readiness | COMPLETE |
| J | Testing | COMPLETE (1160 passing) |
| K | Artifact packaging | COMPLETE |
| L | Commit | PENDING |
