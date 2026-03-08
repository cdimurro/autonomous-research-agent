# Phase 4C Live Validation Report

## Environment
- **Generation model**: qwen3.5:9b-q4_K_M (Ollama, local)
- **Embedding model**: nomic-embed-text (Ollama, 768d, local)
- **Domain**: clean-energy
- **Prior candidates in DB**: 115 (from 20+ prior runs)
- **Findings bootstrapped**: 18

## Run Summary

| Run | Mode | Candidates | Blocked | Warned | Max Sim | Status |
|-----|------|-----------|---------|--------|---------|--------|
| shadow_0 | production_shadow | 5 | 5 | 0 | 0.950 | no_pub |
| shadow_1 | production_shadow | 5 | 4 | 1 | 0.938 | completed |
| shadow_2 | production_shadow | 4 | 4 | 0 | 0.939 | no_pub |
| shadow_3 | production_shadow | 5 | 5 | 0 | 0.965 | no_pub |
| shadow_4 | production_shadow | 5 | 5 | 0 | 0.955 | no_pub |
| review_0 | production_review | 5 | 5 | 0 | 0.940 | no_pub |
| review_1 | production_review | 5 | 4 | 1 | 0.946 | draft |
| review_2 | production_review | 5 | 3 | 2 | 0.965 | draft |

**Totals**: 8 runs, 39 candidates evaluated, 35 blocked (90%), 4 warned (10%), 2 drafts created.

## Key Findings

### 1. Real embeddings catch semantic duplicates the lexical engine misses
The nomic-embed-text model produces cosine similarities of 0.87-0.97 between
semantically similar clean-energy hypotheses. This is qualitatively different
from the mock embedding provider, which would have allowed most of these through.

### 2. Novelty space is saturating for clean-energy domain
With 115 prior candidates in the DB, the LLM generates hypotheses that are
semantically very similar to existing ones. The top repeated nearest neighbors:
- "Waste-Heat Driven Hybrid Electrolysis for Green Hydrogen" (4 appearances)
- "Synergistic Waste Heat Integration for Hybrid Green Fuels" (4 appearances)
- "Thermal-Driven DAC Coupling with Industrial Waste Heat" (4 appearances)

This confirms the embedding novelty engine is working correctly — it's detecting
real conceptual overlap, not false positives.

### 3. Block rate is high but appropriate
90% block rate means the model is re-treading familiar ground. This is a
**generation-side issue**, not a threshold issue. The embedding threshold (0.88)
is correctly flagging near-duplicates.

### 4. Two drafts made it through
Despite high blocking, 2 production_review runs created drafts:
- "Hybrid Offshore Turbine-Wave Converter for Stabilized Electrolysis"
- "Long-Duration Grid Storage using Iron-Air and Sulfide Batteries"

These represent genuinely novel combinations that escaped the embedding filter.

### 5. Domain fit not blocking candidates
All 39 candidates passed the domain-fit gate (0 domain-fit failures).
The clean-energy keywords are well-matched to the LLM's generation tendencies.

## Threshold Assessment

| Threshold | Value | Assessment |
|-----------|-------|------------|
| Embedding block | 0.88 | **Correct** — high similarities are real duplicates |
| Embedding warn | 0.78 | **Correct** — moderate warnings are appropriate |
| Domain-fit min | 0.25 | **Correct** — LLM stays in-domain |
| Publication | 0.60 | **Correct** — passing candidates score well |

**Recommendation**: Do NOT lower the embedding block threshold. Instead, address
novelty saturation by:
1. Expanding the candidate generation prompt to explore different sub-domains
2. Adding a materials-science or cross-domain rotation
3. Periodically archiving old candidates to reduce the prior-art corpus

## Performance
- Average run duration: 176.9s (~3 minutes per run)
- Average candidates per run: 4.9
- Ollama embedding calls: negligible overhead vs generation time

## Drift Analysis
- Average max similarity: 0.950 (very high, indicating saturation)
- Average block rate: 90%
- No significant trend between early and late runs (saturation was already established)
