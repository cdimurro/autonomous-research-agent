# Graph-Native Reasoning Architecture

## Concept Canonicalization (`kg_canonicalization.py`)

### Problem
Raw extracted entities contained:
- **Value-entities**: "2.19 V", "33.7% efficiency", "250k" — bare measurements, not concepts
- **Duplicate names**: "Perovskite Solar Cell" vs "Perovskite Solar Cells" vs "PSCs"
- **Inconsistent naming**: "CO2 Capture" vs "Carbon Capture"

Result: 168 raw entities had only 55 unique canonical names, and 0 cross-paper paths.

### Solution

Three-layer canonicalization:

1. **Value filtering**: Regex patterns reject pure numbers, measurements with units, percentages, scientific notation, and ranges. Filters ~21% of entities.

2. **Synonym resolution**: Domain-specific synonym map normalizes 50+ clean-energy aliases:
   - PSC → perovskite solar cell
   - MOF → metal-organic framework
   - PCE → power conversion efficiency
   - Voc → open-circuit voltage

3. **Stem normalization**: Simple suffix stripping for plurals (cells→cell, batteries→battery).

### Results

| Metric | Before | After |
|--------|--------|-------|
| Raw entities | 208 | — |
| Filtered (values) | — | 44 (21%) |
| Remaining | — | 164 |
| Unique canonical | 55 | 48 |
| Collapse rate | — | 70.7% |
| Cross-paper concepts | 0 | **41** |
| Cross-paper paths | 0 | **30** |

### Canonical Graph (`CanonicalGraph`)

Nodes are deduplicated concepts, edges are relations mapped through entity_id → canonical_name. Self-loops after canonicalization are removed. Undirected traversal for BFS path finding.

## Multi-Hop Reasoning (`CanonicalMultiHopReasoner`)

### Path Finding

BFS-based traversal on the canonical concept graph:
- Supports 2-hop and 3-hop bounded paths
- Deduplication by concept set (frozenset of canonical names)
- Confidence: geometric mean of all node and edge confidences
- Prioritizes cross-paper paths, then template matches, then confidence

### Scientific Motif Templates

Paths are scored against known scientific reasoning patterns:

| Template | Node Types |
|----------|-----------|
| material → property → device | {material, compound, structure} → {property, metric, phenomenon} → {device, technology} |
| catalyst → mechanism → efficiency | {material, compound} → {mechanism, process} → {property, metric} |
| structure → transport → performance | {structure, material} → {mechanism, process, phenomenon} → {property, device} |

### Results

- **30 canonical paths** found (18 2-hop, 12 3-hop)
- **All 30 are cross-paper** — canonicalization made this possible
- **1 template match** (catalyst → mechanism → efficiency)
- **Mean confidence: 0.9111**

## Cross-Paper Subgraph Construction (`kg_subgraph.py`)

### Subgraph Builder

Builds compact evidence neighborhoods from the canonical graph:

1. **Seed expansion**: BFS from seed concepts, prioritizing cross-paper and mechanistic edges
2. **Topic matching**: Find concepts matching topic keywords, expand neighborhood
3. **Cross-paper focus**: Prioritize edges bridging different papers

### Evidence Conversion

Subgraphs convert to:
- `EvidenceItem` (source_type="kg_subgraph") for retrieval integration
- Prompt blocks for graph-conditioned generation

### Prompt Format

```
GRAPH NEIGHBORHOOD: perovskite solar cell efficiency
  Concepts (6):
    - perovskite tandem solar cell (device) [9p]
    - open-circuit voltage (property) [9p]
    - single-junction solar cell (device) [9p]
    - ...
  Relations (8):
    - perovskite tandem solar cell [enhances] open-circuit voltage [CROSS-PAPER]
    - ...
  Cross-paper connections: 4
  Papers involved: 9
```
