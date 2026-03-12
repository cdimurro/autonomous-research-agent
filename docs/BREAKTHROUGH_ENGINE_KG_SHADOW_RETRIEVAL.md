# KG Shadow Retrieval — Phase 10A

## Overview

KGEvidenceSource implements the EvidenceSource ABC, enabling drop-in shadow evaluation against the current production retrieval path without any production switch.

## Shadow Mode

- KGEvidenceSource is **not** registered in the production CompositeRetrievalSource
- It can be invoked independently via CLI: `python -m breakthrough_engine kg compare`
- The comparison harness runs both paths side by side and exports artifacts

## Evidence Gathering Strategy

### 1. Paper Segments (primary)
- Reads from `bt_paper_segments` with status scored/extracted
- Filters by domain and min_relevance threshold
- Returns compressed text when available, raw text otherwise
- source_type: `kg_segment`

### 2. Graph Context (enrichment)
- Reads from `bt_kg_entities` + `bt_kg_relations`
- Builds evidence items from entity-relation pairs
- Provides structured scientific context
- source_type: `kg_graph`

### 3. Upstream Findings (fallback)
- Optionally reads from upstream findings table
- Enabled via `include_upstream_findings=True`
- source_type: `finding`

## Comparison Harness

### Metrics Compared
- **Item count**: How many evidence items each source returns
- **Mean relevance**: Average relevance score
- **Source diversity**: Unique source IDs
- **Source type balance**: Distribution of source_types
- **Quote length**: Mean quote length (proxy for content density)

### Verdicts
- `shadow_better`: KG retrieval outperforms on majority of metrics
- `current_better`: Current retrieval outperforms
- `comparable`: No clear winner
- `shadow_empty`: KG retrieval returned no items
- `current_empty`: Current retrieval returned no items

### Export Formats
- JSON: Machine-readable comparison result
- Markdown: Human-readable report
- CSV: Tabular summary for spreadsheet analysis

## CLI Usage

```bash
# Compare current vs KG shadow retrieval
python -m breakthrough_engine kg compare --domain clean-energy --limit 20

# Output goes to runtime/kg_comparisons/ by default
```

## Production Switch Criteria (Future)

KG retrieval should only replace production retrieval when:
1. Shadow comparison shows `shadow_better` consistently
2. Mean relevance improvement > 5%
3. Source diversity is equal or better
4. No regression in downstream candidate quality
5. Manual operator review confirms improvement
