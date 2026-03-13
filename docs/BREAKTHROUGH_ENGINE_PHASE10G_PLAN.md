# Phase 10G: Limited Production Retrieval A/B Plan

**Date:** 2026-03-13
**Branch:** `breakthrough-engine-phase10g-retrieval-ab`
**Base:** `breakthrough-engine-phase10a-kg-shadow` @ `34730a1`

## Objective

Run the first limited production-style retrieval A/B comparing current retrieval
(ExistingFindingsSource + flat generation) against graph-native retrieval
(HybridKGEvidenceSource + graph-conditioned generation). Policy, embedding, and
model are held constant. The only experimental variable is the retrieval path.

## Arms

| Arm | Evidence Source | Generation Template | Graph Context |
|-----|----------------|-------------------|--------------|
| **current** | ExistingFindingsSource | EVIDENCE_BLOCK_TEMPLATE (flat) | No |
| **graph_native** | HybridKGEvidenceSource | GRAPH_CONDITIONED_TEMPLATE | Yes |

## Held Constant

| Parameter | Value |
|-----------|-------|
| Policy | evidence_diversity_v1 (champion) |
| Embedding | qwen3-embedding:4b (Regime 2) |
| Generation model | qwen3.5:9b-q4_K_M |
| Candidate budget | 7 per stage |
| Domain | clean-energy |
| Labeling schema | approve/reject/defer + confidence scores |

## Run Plan

- 6 campaigns per arm (12 total)
- All use `LadderConfig(mode="benchmark")` for reproducibility
- Graph arm uses `evidence_source_override` + `enable_graph_context=True`
- Auto-labeling from scoring signals (same method as Phase 10C)

## Metrics Collected Per Campaign

- campaign_id, arm, status, elapsed_seconds
- champion_title, champion_score
- finalist_count, candidate_count
- evidence_items, unique_sources, source_types
- top_source_concentration
- novelty_score, plausibility_score, evidence_strength_score
- grounding_quality (graph arm only)

## Decision Criteria

| Check | Threshold | Action |
|-------|-----------|--------|
| Score preservation | >= current - 0.01 | Required for promotion |
| Approval rate | >= 60% | Required for promotion |
| Score regression | > 0.05 below current | Reject |
| Approval rate | < 40% | Reject |
| Diversity improvement | > current | Favors promotion |
| Grounding quality | > 0 strong support | Favors promotion |

## Deliverables

- A: Experiment branch + comparability lock
- B: Production safety guardrails
- C: Limited A/B execution (6+6)
- D: Review label collection
- E: Comparison summary
- F: Switch decision
- G: Rollback/reversion readiness
- H: Testing
- I: Artifact packaging
- J: Commit
