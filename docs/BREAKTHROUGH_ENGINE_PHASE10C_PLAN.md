# Phase 10C Plan: Retrieval A/B Trial

## Objective

Run a controlled 6+6 A/B trial to determine whether KG retrieval preserves or improves downstream candidate quality compared to current production retrieval.

## Design

- Control arm: ExistingFindingsSource (current production)
- Treatment arm: KGEvidenceSource (shadow KG)
- Fixed: evidence_diversity_v1 policy, qwen3-embedding:4b, qwen3.5:9b-q4_K_M
- Only variable: evidence source

## Status

**COMPLETE** — Recommendation: `keep_shadow_only`

See `docs/BREAKTHROUGH_ENGINE_PHASE10C_STATUS.md` for full results.
