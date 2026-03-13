# Graph-Conditioned Generation

## Overview

Phase 10E-Prime adds structured graph context to hypothesis generation. Instead of just flat evidence snippets, the LLM receives:

1. **Curated findings** (existing production evidence)
2. **KG segments** (machine-extracted passages)
3. **Graph paths** (multi-hop reasoning chains between concepts)
4. **Subgraph neighborhoods** (structured concept graphs around a topic)

## Source Type Labels

Each evidence item carries a type label in the generation prompt:

| Source Type | Label | Trust Level |
|-------------|-------|-------------|
| finding | `[CURATED_FINDING]` | 1.00 |
| paper | `[PAPER]` | 0.95 |
| kg_segment | `[KG_SEGMENT]` | 0.85 |
| kg_graph | `[KG_RELATION]` | 0.80 |
| graph_path | `[GRAPH_PATH]` | 0.75 |
| kg_synthesis | `[CROSS_PAPER_SYNTHESIS]` | 0.70 |
| kg_subgraph | `[GRAPH_NEIGHBORHOOD]` | 0.72 |

## Graph-Conditioned Template

The `GRAPH_CONDITIONED_TEMPLATE` includes:
- A structured graph context block (from subgraph's `to_prompt_block()`)
- Evidence items with type labels and confidence
- Explicit instructions to:
  - Use graph structure to identify non-obvious cross-paper connections
  - Prioritize cross-paper connections marked `[CROSS-PAPER]`
  - Explain mechanistic reasoning chains
  - Identify supporting cross-paper connections
  - Specify testable experimental timeframes

## Comparison: Flat vs Graph-Conditioned

| Aspect | Flat Evidence | Graph-Conditioned |
|--------|--------------|-------------------|
| Input structure | Numbered list of quotes | Structured graph + numbered list |
| Cross-paper visibility | Implicit (LLM must infer) | Explicit (marked `[CROSS-PAPER]`) |
| Mechanistic chains | Not visible | Visible as graph paths |
| Entity relations | Not visible | Visible in subgraph |
| Source diversity | Type labels only | Type labels + graph structure |
| Context size | ~2-3K tokens | ~3-5K tokens |

## Usage

The graph-conditioned prompt is built via:
```python
prompt = generator._build_graph_conditioned_prompt(
    evidence=evidence_items,
    domain="clean-energy",
    budget=10,
    graph_context=subgraph.to_prompt_block(),
)
```

This keeps the existing flat generation path available for comparison (A/B).
