# Policy Actuation Matrix — Phase 9

**Last Updated**: 2026-03-10 (Phase 9 implementation)
**Champion**: phase5_champion
**Challenger**: synthesis_focus_v1

---

## Actuation Matrix

| Policy Surface | Phase 8B Status | Phase 9 Status | Where Wired | Test Coverage |
|----------------|-----------------|----------------|-------------|---------------|
| `scoring_weights` | WIRED | WIRED | daily_search._apply_policy() → ResearchProgram.scoring_weights → score_candidate() → compute_final() | test_policy_registry.py |
| `generation_prompt_variant` | INERT | WIRED (Phase 9) | OllamaCandidateGenerator(prompt_variant=) → _call_ollama(system_prompt=) | test_policy_actuation.py |
| `evidence_ranking_weights` | INERT | WIRED (Phase 9) | orchestrator → rank_evidence(evidence_ranking_weights=) | test_policy_actuation.py |
| `sub_domain_rotation_policy` | PARTIALLY WIRED | WIRED (Phase 9) | orchestrator → diversity_engine.build_context(rotation_policy=) | test_policy_actuation.py |
| `diversity_steering_variant` | INERT | DEFERRED | No implementation in DiversityEngine | - |
| `negative_memory_strategy` | INERT | DEFERRED | RunMemory has no variant logic | - |
| `bridge_selection_policy` | INERT | DEFERRED | SynthesisEngine has no variant logic | - |
| `review_gating_heuristics` | INERT | DEFERRED | Not used at runtime | - |

---

## Surface Detail

### 1. scoring_weights (WIRED, Phase 8B)

**How it works**:
```
PolicyConfig.scoring_weights
  → daily_search._apply_policy(program, policy)
    → ResearchProgram(scoring_weights=new_weights)  # new program copy
      → BreakthroughOrchestrator(program=trial_program)
        → score_candidate(program=self.program)
          → score.compute_final(program.scoring_weights)
```

**Champion values** (defaults):
```json
{
  "novelty": 0.20, "plausibility": 0.20, "impact": 0.20,
  "evidence_strength": 0.20, "simulation_readiness": 0.10, "inverse_validation_cost": 0.10
}
```

**synthesis_focus_v1 values**:
```json
{
  "novelty": 0.18, "plausibility": 0.25, "impact": 0.20,
  "evidence_strength": 0.20, "simulation_readiness": 0.12, "inverse_validation_cost": 0.05
}
```

**Key delta**: plausibility +25%, simulation_readiness +20%, inverse_validation_cost -50%, novelty -10%

---

### 2. generation_prompt_variant (WIRED, Phase 9)

**System prompt variants**:

| Variant | File Key | Description |
|---------|----------|-------------|
| `standard` | CANDIDATE_GENERATION_PROMPT | Standard hypothesis generation |
| `synthesis_focus` | CANDIDATE_GENERATION_PROMPT_SYNTHESIS_FOCUS | Emphasizes mechanism plausibility and testability |
| `evidence_heavy` | CANDIDATE_GENERATION_PROMPT_EVIDENCE_HEAVY | Emphasizes grounding in provided evidence |

**How it works** (Phase 9):
```
PolicyConfig.generation_prompt_variant
  → BreakthroughOrchestrator.__init__(policy_config=policy_config)
    → OllamaCandidateGenerator(prompt_variant=policy_config.generation_prompt_variant)
      → self.prompt_variant stored in generator
        → generate() → PROMPT_VARIANTS[self.prompt_variant]
          → _call_ollama(system_prompt=selected_prompt)
```

**synthesis_focus variant adds**:
- Explicit emphasis on mechanism plausibility ("Why should this work physically/chemically?")
- Explicit emphasis on testability window ("What is the shortest path to experimental validation?")
- Explicit emphasis on cross-domain synthesis and novel connections
- Deprioritizes: vague claims, untestable timelines, analogical reasoning without mechanism

---

### 3. evidence_ranking_weights (WIRED, Phase 9)

**Default weights in rank_evidence()**:
```python
api_score * 0.35 + domain_overlap * 0.30 + mech_overlap * 0.20 + recency_bonus + baseline * 0.075
```

**Configurable via**:
```json
"evidence_ranking_weights": {
  "api_relevance": 0.35,
  "domain_overlap": 0.30,
  "mechanism_overlap": 0.20,
  "baseline": 0.15
}
```

**How it works** (Phase 9):
```
PolicyConfig.evidence_ranking_weights
  → BreakthroughOrchestrator._execute_cycle()
    → rank_evidence(items, domain, mechanism, evidence_ranking_weights=self.policy_config.evidence_ranking_weights)
      → uses provided weights instead of hardcoded defaults
```

**synthesis_focus_v1 does NOT override evidence_ranking_weights** (uses None → defaults). This is correct — synthesis focus is primarily about generation emphasis and scoring, not evidence selection.

---

### 4. sub_domain_rotation_policy (WIRED, Phase 9)

**How it works** (Phase 9):
```
PolicyConfig.sub_domain_rotation_policy  # "auto" | "fixed" | "random"
  → BreakthroughOrchestrator._execute_cycle()
    → diversity_engine.build_context(rotation_policy=self._effective_rotation_policy())
```

**Champion**: "auto" (rounds-robin through sub-domains)
**synthesis_focus_v1**: "auto" (same — not a differentiating factor for this challenger)

---

## Policy Snapshot Logging (Phase 9)

Each orchestrator run now logs a policy snapshot at start:
```
[run_id] Policy snapshot: id=<id> generation_prompt_variant=<v> scoring_weights=<w>
```

This makes effective policy usage visible in artifacts and logs.

---

## Deferred Surfaces

### diversity_steering_variant
Currently: `DiversityEngine.build_context()` returns excluded topics based on blocked candidates. No "aggressive/conservative" variant logic exists. Implementing this would require defining how "aggressive" steering differs (e.g., more excluded topics, stronger addendum language). Deferred to Phase 10.

### negative_memory_strategy
Currently: `RunMemory` uses a fixed strategy for loading negative examples. The "standard/strict/permissive" variants are registered but no code branch exists. Deferred to Phase 10.

### bridge_selection_policy
Currently: `SynthesisEngine` always uses "auto" bridge selection. "Fixed" and "random" variants would need SynthesisEngine changes. Deferred to Phase 10 (synthesis-focused phase).

### review_gating_heuristics
Currently: Review gating uses fixed thresholds. Deferred to Phase 10.

---

## Impact Assessment

For `synthesis_focus_v1`, the Phase 9 actuated surfaces are:

| Surface | Actuated? | Expected Behavioral Impact |
|---------|-----------|---------------------------|
| generation_prompt_variant="synthesis_focus" | YES (Phase 9) | LLM generates candidates with stronger mechanism detail and clearer testability |
| scoring_weights (plausibility +25%, sim_readiness +20%) | YES (Phase 8B) | Candidates with detailed mechanisms rank higher even with lower novelty |
| evidence_ranking_weights=None | N/A | No change from champion |
| sub_domain_rotation_policy="auto" | Same as champion | No differential effect |

**Net effect**: The challenger now differs from the champion in two meaningful ways:
1. The prompt *asks for* higher plausibility emphasis
2. The scoring *rewards* higher plausibility emphasis

This creates a genuine hypothesis: "Does emphasizing mechanism plausibility in both prompt and scoring produce candidates that reviewers approve at higher rates?"
