# Evidence Grounding and Contradiction Validation

## Purpose

The grounding validator checks whether evidence actually supports the hypotheses it's attached to. This is critical for trust — without it, the system can generate plausible-sounding hypotheses from weakly related evidence.

## Validation Pipeline

For each candidate hypothesis + evidence set:

1. **Extract claim keywords** from statement, mechanism, expected_outcome
2. **For each evidence item:**
   - Extract evidence keywords from title and quote
   - Compute keyword overlap (Jaccard-like, normalized by claim keywords)
   - Apply source trust prior by source_type
   - Compute grounding score: `overlap * 0.6 + trust * 0.2 + relevance * 0.2`
   - Phase 10E-Prime: structural coherence bonus for graph evidence with high overlap (+0.05)
   - Check for contradiction patterns (negation words near claim terms)
   - Assign verdict: strong_support / weak_support / unsupported / contradicted

3. **Aggregate:**
   - Mean grounding score across evidence items
   - Overall verdict based on strong/contradicted balance

## Trust Priors by Source Type

| Source Type | Trust Prior | Rationale |
|-------------|------------|-----------|
| finding | 0.90 | Curated, peer-reviewed findings |
| paper | 0.85 | Direct paper citations |
| kg_segment | 0.70 | Machine-extracted passages |
| kg_graph | 0.60 | Graph-derived entity/relation |
| graph_path | 0.55 | Multi-hop reasoning paths |
| kg_subgraph | 0.52 | Subgraph-derived evidence |
| kg_synthesis | 0.50 | Cross-paper synthesis |

## Verdict Thresholds

| Verdict | Condition |
|---------|-----------|
| `strong_support` | grounding >= 0.5, no contradiction |
| `weak_support` | grounding >= 0.3, no contradiction |
| `unsupported` | grounding < 0.3 |
| `contradicted` | contradiction pattern + claim overlap >= 2 words → 0.3x penalty |

## Contradiction Detection

Patterns checked: `fail|failed|disproven|refuted|incorrect|impossible`, `no effect|no improvement|no evidence`, `contrary|opposite|reverse|decrease|degrade`

A contradiction is flagged only when:
1. A negation pattern appears in the evidence text
2. At least 2 words from the candidate's claim appear within 50 characters of the negation

## Current Results

With graph-native evidence (10 path items + 2 subgraph items):
- **Overall verdict:** `weak_support`
- **Grounding score:** 0.393
- **Interpretation:** The graph evidence provides partial keyword overlap with the test hypothesis. The score is reasonable for machine-derived evidence — curated findings score higher (0.90 trust vs 0.55 for graph_path).

## Structural Coherence Bonus

Phase 10E-Prime adds a +0.05 bonus to graph evidence (graph_path, kg_synthesis, kg_subgraph) when keyword overlap exceeds 0.3. This rewards graph paths that are topically relevant to the claim, distinguishing them from random graph traversals.
