# Phase 10A: KG Shadow Foundation — Plan

## Objective

Build a comprehensive knowledge graph foundation that can eventually improve candidate quality, evidence quality, and retrieval scale — but do it safely in shadow mode.

## Deliverables

| # | Deliverable | Module | Status |
|---|-------------|--------|--------|
| A | Paper segment staging | `paper_ingestion.py` | COMPLETE |
| B | Entity/relation extraction | `kg_extractor.py` | COMPLETE |
| C | KG shadow retrieval | `kg_retrieval.py` | COMPLETE |
| D | Comparison harness | `kg_comparison.py` | COMPLETE |
| E | Write-back scaffolding | `kg_writer.py` | COMPLETE |
| F | Throughput safety | Sequential worker design | COMPLETE |
| G | Offline-safe tests | `test_phase10a.py` | COMPLETE (57 tests) |
| H | Branch strategy | `breakthrough-engine-phase10a-kg-shadow` | COMPLETE |

## Implementation Order

1. Migration 12: bt_paper_segments, bt_kg_entities, bt_kg_relations, bt_kg_findings
2. Paper ingestion worker with segment scoring
3. Entity/relation extraction pipeline (mock + LLM)
4. KGEvidenceSource implementing EvidenceSource ABC
5. Shadow comparison harness (JSON/MD/CSV export)
6. Write-back scaffolding with temporal design
7. Tests and documentation

## Constraints

- No merge to main
- No production pipeline switch
- No 768d/2560d embedding mixing
- All tests offline-safe
- One-publication-per-run invariant preserved
- Ollama single-concurrency respected

## Branch

`breakthrough-engine-phase10a-kg-shadow` (from `c84bc71`)
