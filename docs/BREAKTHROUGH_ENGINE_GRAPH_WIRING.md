# Graph-Native Pipeline Wiring Audit

**Phase:** 10F
**Date:** 2026-03-12
**Auditor:** Claude Opus 4.6

## Wiring Matrix (Pre-Phase 10F)

| Component | Code Exists | Called in Shadow Path | Called in Production Path | Status |
|-----------|-------------|----------------------|--------------------------|--------|
| `HybridKGEvidenceSource` | YES (`hybrid_retrieval.py`) | NO | NO | DEAD CODE |
| `GRAPH_CONDITIONED_TEMPLATE` | YES (`candidate_generator.py:193`) | NO | NO | DEAD CODE |
| `_build_graph_conditioned_prompt()` | YES (`candidate_generator.py:359`) | NO | NO | DEAD CODE |
| `CanonicalMultiHopReasoner` | YES (`kg_reasoning.py`) | NO (script only) | NO | DEAD CODE |
| `SubgraphBuilder` | YES (`kg_subgraph.py`) | NO (script only) | NO | DEAD CODE |
| `EvidenceGroundingValidator` | YES (`kg_grounding.py`) | NO | NO | DEAD CODE |
| `_SOURCE_TYPE_LABELS` in formatting | YES (`candidate_generator.py:163`) | YES | YES | WIRED |
| `kg_subgraph` trust in scoring | YES (`scoring.py:60`) | YES (if items present) | YES | WIRED (inert) |
| `ExistingFindingsSource` | YES | YES | YES | WIRED |
| `SemanticScholarRetrievalSource` | YES | YES (if API key set) | YES | WIRED |

## Execution Path Trace (Shadow Campaign)

```
CLI: python -m breakthrough_engine daily run <profile>
  -> DailySearchLadder.run_campaign()
    -> _run_single_trial(repo, program, policy)
      -> BreakthroughOrchestrator(program, repo, policy_config=policy)
        -> evidence_source = ExistingFindingsSource(repo.db)  [HARDCODED]
        -> generator = OllamaCandidateGenerator(prompt_variant="standard")
      -> orch.run() -> _execute_cycle()
        -> Step 1: evidence = self.evidence_source.gather("clean-energy", limit=20)
           -> SQL: findings WHERE judge_verdict='accepted'  [NO KG EVIDENCE]
        -> Step 2: candidates = generator.generate(evidence, ...)
           -> user_message = EVIDENCE_BLOCK_TEMPLATE.format(...)  [FLAT TEMPLATE]
           -> system_prompt = PROMPT_VARIANTS["standard"]
           -> _call_ollama(system_prompt, user_message)  [NO GRAPH CONTEXT]
        -> Step 5: _run_evidence_gate()
           -> rank_evidence(evidence, evidence_ranking_weights=policy_erw)
           -> EvidencePack(items=ranked_items)  [ONLY FINDINGS]
        -> Step 6: score_candidate(evidence_pack=pack)
           -> _SOURCE_TRUST used but no graph items present  [INERT]
```

## Gap Analysis

### Gap 1: No evidence-source injection mechanism
The orchestrator chooses evidence source based on `RunMode` only. No mechanism to say "use hybrid KG source for this shadow run."

**Fix:** Add `evidence_source_override` parameter to `_run_single_trial()` and propagate to `BreakthroughOrchestrator.__init__()`.

### Gap 2: No graph context in generation
`generate()` always uses `EVIDENCE_BLOCK_TEMPLATE`. The `_build_graph_conditioned_prompt()` method exists but has no caller.

**Fix:** Add `graph_context` parameter to `generate()`. When present, use `GRAPH_CONDITIONED_TEMPLATE` instead.

### Gap 3: No graph evidence construction in orchestrator
The orchestrator doesn't build canonical paths or subgraphs. Graph construction only happens in standalone scripts.

**Fix:** Add a `_build_graph_context()` method to the orchestrator that constructs canonical graph + paths + subgraph when graph mode is enabled.

### Gap 4: Grounding not used in pipeline
`EvidenceGroundingValidator` exists but is never called during runs.

**Fix:** Call grounding validation in the scoring step and log results.

## Wiring Matrix (Post-Phase 10F Target)

| Component | Shadow Path | Production Path |
|-----------|-------------|-----------------|
| `HybridKGEvidenceSource` | WIRED (when graph mode enabled) | UNCHANGED |
| `GRAPH_CONDITIONED_TEMPLATE` | WIRED (when graph evidence present) | UNCHANGED |
| `_build_graph_conditioned_prompt()` | WIRED (via generate(graph_context=)) | UNCHANGED |
| `CanonicalMultiHopReasoner` | WIRED (via orchestrator graph build) | UNCHANGED |
| `SubgraphBuilder` | WIRED (via orchestrator graph build) | UNCHANGED |
| `EvidenceGroundingValidator` | WIRED (in scoring step) | UNCHANGED |
