# Phase 10E: KG Reasoning Architecture

## Multi-Hop Graph Reasoning

### Graph Construction (`KGGraphBuilder`)

Builds an in-memory adjacency graph from `bt_kg_entities` and `bt_kg_relations`:
- **Nodes**: `GraphNode` with entity metadata (type, name, confidence, paper_id, segment_id)
- **Edges**: `GraphEdge` with relation type, confidence, and directional source/target
- Loads domain-filtered, status='extracted' entities and relations

### Path Finding (`MultiHopReasoner`)

BFS-based traversal finding paths of 2-3 hops between entities:
- Configurable `max_hops` (default 2) and `min_path_confidence` (default 0.15)
- **Path confidence**: geometric mean of edge confidences × node confidences along the path
- **Cross-paper detection**: flags paths where nodes span different `paper_id` values
- Outputs `ReasoningPath` with `to_evidence_item()` for integration with retrieval

### Cross-Paper Synthesis (`CrossPaperSynthesizer`)

Finds bridges between papers via shared concepts:
1. **Shared-concept bridges**: entities from different papers with matching `canonical_name`
2. **1-hop bridges**: entity pairs connected by a relation that span different papers
- Outputs `SynthesisLink` with `to_evidence_item()` (source_type="kg_synthesis")

### Current Limitations

- **0 cross-paper paths found** in actual data — 27 extracted segments yield 168 entities but entity names don't match across papers without stronger canonicalization
- **20 synthesis links found** — the 1-hop bridge approach works even with current entity naming
- All 50 multi-hop paths are 2-hop, same-paper connections

## Multi-Signal Segment Scoring

### Signals (`kg_segment_scorer.py`)

| Signal | Weight | Detection Method |
|--------|--------|-----------------|
| Embedding similarity | 0.30 | Cosine similarity to domain anchor (from DB) |
| Keyword overlap | 0.20 | Domain keyword set matching (30 clean-energy terms) |
| Quantitative density | 0.20 | Regex patterns for units, percentages, scientific notation |
| Citation density | 0.10 | Reference markers ([1], (2024), et al., DOI) |
| Mechanism specificity | 0.20 | Causal/mechanistic keyword presence (28 terms) |

### Score Distribution Analysis

Current data shows most segments score lower on composite (mean 0.4398) than on embedding-only (mean 0.5835). This is correct behavior — segments with high embedding similarity but no quantitative results, citations, or mechanistic language are lower-quality evidence and the composite score reflects this.

## Evidence Grounding Validation

### Validator (`kg_grounding.py`)

Checks whether evidence actually supports the hypothesis it's attached to:
- **Grounding score**: `overlap * 0.6 + trust * 0.2 + relevance * 0.2`
- **Contradiction detection**: regex patterns for negation words near claim-related terms
- **Trust priors**: finding=0.90, paper=0.85, kg_segment=0.70, kg_graph=0.60, graph_path=0.55, kg_synthesis=0.50

### Verdicts

| Verdict | Condition |
|---------|-----------|
| `strong_support` | grounding >= 0.5, no contradiction |
| `weak_support` | grounding >= 0.3, no contradiction |
| `unsupported` | grounding < 0.3 |
| `contradicted` | contradiction signal detected (0.3x penalty) |

## Source-Type-Aware Scoring

### Trust Weights in `scoring.py`

Evidence strength now uses trust-weighted relevance: `relevance * trust_prior`

| Source Type | Trust Prior | Rationale |
|-------------|------------|-----------|
| finding | 1.00 | Curated, accepted findings |
| paper | 0.95 | Direct paper citations |
| journal | 0.95 | Journal-level references |
| kg_segment | 0.85 | Machine-extracted segments |
| kg_graph | 0.80 | Graph-derived entity/relation |
| graph_path | 0.75 | Multi-hop reasoning paths |
| kg_synthesis | 0.70 | Cross-paper synthesis |
| (default) | 0.90 | Unknown/external sources |

### Enhanced Diversity Bonus

`min(0.25, source_id_count * 0.04 + source_type_count * 0.03)`

Rewards both source ID diversity and source type diversity, encouraging hybrid evidence packs.

## Source-Aware Generation

### Labels in `candidate_generator.py`

Evidence items now carry `[TYPE_LABEL]` prefixes in generation prompts:
- `[CURATED_FINDING]`, `[PAPER]`, `[KG_SEGMENT]`, `[KG_GRAPH]`, `[GRAPH_PATH]`, `[KG_SYNTHESIS]`

The generation prompt includes an EVIDENCE TYPE KEY and instructions to prefer combining curated findings with KG-derived insights for stronger hypotheses.
