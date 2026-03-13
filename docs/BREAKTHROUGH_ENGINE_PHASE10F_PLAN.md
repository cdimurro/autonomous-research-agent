# Phase 10F: Graph-Conditioned Pipeline Wiring, Grounding Hardening, and Post-Wiring Shadow A/B

**Branch:** `breakthrough-engine-phase10a-kg-shadow`
**Start commit:** `d5896c9`
**Date:** 2026-03-12

## Problem Statement

Phase 10E-Prime built graph-native evidence (canonicalization, multi-hop reasoning, subgraphs) and showed retrieval-level improvement (hybrid 0.885 > current 0.879). However, honest inspection reveals the graph-native path is NOT wired into the actual production/shadow pipeline:

1. `_build_graph_conditioned_prompt()` is dead code — never called by the orchestrator
2. `HybridKGEvidenceSource` is never injected through the real evidence-source path
3. The 3+3 campaign comparison ran both arms through identical pipelines
4. Grounding remains weak (10/12 items unsupported)
5. Near-duplicate concepts dilute graph reasoning quality

## Objective

Wire the KG into the actual generation pipeline, improve grounding quality, and run a fair post-wiring comparison to determine if the KG materially improves downstream outcomes.

## Deliverables

| # | Deliverable | Priority |
|---|-------------|----------|
| A | Graph path wiring audit | P1 |
| B | Evidence-source injection into real shadow runs | P1 |
| C | Graph-conditioned generation wiring | P2 |
| D | Canonicalization hardening | P2 |
| E | Grounding hardening | P2 |
| F | Graph-aware downstream scoring integration | P2 |
| G | Post-wiring retrieval/generation shadow comparison | P3 |
| H | Bounded downstream shadow campaign comparison | P3 |
| I | Switch-readiness decision | P4 |
| J | Write-back memory loop status | P4 |
| K | Testing | P4 |
| L | Artifact packaging | P4 |
| M | Branch/commit strategy | P4 |

## Implementation Strategy

### P1: Make the Graph Reachable
- Add `evidence_source_override` field to orchestrator construction path
- Support `shadow_graph_native` mode in `_run_single_trial()`
- Inject `HybridKGEvidenceSource` when shadow mode + graph enabled
- Log effective evidence source per run

### P2: Make the Graph Visible to the LLM
- Add `graph_context` parameter to `generate()` method
- When graph evidence is present, use `GRAPH_CONDITIONED_TEMPLATE` instead of flat template
- Build graph context from canonical paths + subgraphs in orchestrator `_execute_cycle()`
- Improve canonicalization (merge near-duplicates) and grounding (better overlap scoring)

### P3: Measure the Difference
- Run retrieval/generation comparison v5 with actual wiring
- Run bounded 3+3 downstream campaign comparison with graph arm using real graph path
- Capture champion scores, review labels, and evidence composition

### P4: Decide and Document
- Produce switch-readiness recommendation
- Package artifacts
- Update docs and commit

## Constraints
- Do not merge to main
- Do not switch live production retrieval
- Policy fixed to evidence_diversity_v1
- All tests offline-safe
- Keep graph wiring explicit, auditable, and reversible
