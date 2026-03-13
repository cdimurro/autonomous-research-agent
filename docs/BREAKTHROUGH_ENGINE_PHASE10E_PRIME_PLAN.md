# Phase 10E-Prime: Graph-Native Reasoning — Plan

**Branch:** `breakthrough-engine-phase10a-kg-shadow`
**Goal:** Turn the KG into a graph-native reasoning system that can beat production through structural reasoning and grounded cross-paper synthesis, not just different evidence.

## Strategic Insight

The KG will not win by being a "different evidence table." It will only win by doing what flat findings retrieval cannot:
1. Canonicalize concepts across papers
2. Reason over multi-hop relations
3. Synthesize cross-paper support structures
4. Condition hypothesis generation on graph structure
5. Validate claim grounding against graph-backed support
6. Write useful outputs back into graph memory

## Deliverables

| ID | Deliverable | Status |
|----|------------|--------|
| A | Concept canonicalization layer | DONE — `kg_canonicalization.py` |
| B | Graph quality and coverage upgrade | DONE — extraction running + coverage report |
| C | Multi-hop canonical graph reasoning | DONE — `kg_reasoning.py` (CanonicalMultiHopReasoner) |
| D | Cross-paper subgraph construction | DONE — `kg_subgraph.py` |
| E | Graph-conditioned generation inputs | DONE — `candidate_generator.py` modified |
| F | Evidence grounding + contradiction validation | DONE — `kg_grounding.py` modified |
| G | Graph-aware evidence strength | DONE — `scoring.py` modified |
| H | Graph memory loop preparation | DONE — `kg_writer.py` modified |
| I | Retrieval/generation comparison v4 | DONE — pipeline + artifacts |
| J | Downstream campaign comparison | DONE — 3+3 campaign script |
| K | Production-surpass readiness decision | DONE — `ready_for_limited_production_retrieval_ab` |
| L | Testing (offline-safe) | DONE — 41 new tests, 1119 total |
| M | Artifact packaging and docs | DONE |

## Constraints

- Do NOT merge to main
- Do NOT switch production retrieval
- Policy fixed: evidence_diversity_v1
- Embedding: qwen3-embedding:4b (Regime 2)
- All tests offline-safe
- One-publication-per-run invariant preserved
