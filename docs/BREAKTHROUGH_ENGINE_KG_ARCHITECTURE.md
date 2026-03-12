# KG Architecture — Phase 10A

## Overview

The KG shadow foundation adds four bt_-prefixed tables and five new modules to the Breakthrough Engine, enabling structured knowledge representation without modifying the production pipeline.

## Tables (Migration 12)

```
bt_paper_segments
  ├── id, paper_id, source_id, segment_index
  ├── raw_text, compressed_text, relevance_score
  ├── domain, status, embedding_json
  └── ingested_at, summarized_at, error_message

bt_kg_entities
  ├── id, segment_id, paper_id
  ├── entity_type, name, canonical_name, description
  ├── confidence, domain, status
  └── extracted_at, error_message

bt_kg_relations
  ├── id, segment_id, paper_id
  ├── source_entity_id, target_entity_id
  ├── relation_type, description, confidence
  ├── domain, status
  └── extracted_at, error_message

bt_kg_findings
  ├── id, candidate_id, publication_id
  ├── title, statement, mechanism, domain, confidence
  ├── valid_from, valid_until, superseded_by
  ├── source_evidence_ids, status
  └── created_at
```

## Module Architecture

```
paper_ingestion.py
  ├── segment_text()           — bounded text segmentation
  ├── SegmentRelevanceScorer   — embedding similarity to domain anchor
  ├── compress_segment()       — optional Ollama compression
  └── PaperIngestionWorker     — full ingestion pipeline

kg_extractor.py
  ├── EntityRelationExtractor  — LLM-based extraction pipeline
  ├── MockEntityRelationExtractor — offline-safe deterministic extractor
  └── _parse_extraction_response() — JSON fallback parsing

kg_retrieval.py
  └── KGEvidenceSource(EvidenceSource)
      ├── _gather_from_segments()  — bt_paper_segments → EvidenceItem
      ├── _gather_from_graph()     — entity+relation → EvidenceItem
      └── _gather_upstream_findings() — upstream fallback

kg_comparison.py
  ├── SourceMetrics            — per-source statistics
  ├── ComparisonResult         — full comparison result
  └── RetrievalComparisonHarness
      ├── compare()            — side-by-side evaluation
      ├── export_json()        — JSON artifact
      ├── export_markdown()    — human-readable report
      └── export_csv()         — tabular export

kg_writer.py
  ├── write_candidate_as_finding()     — candidate → bt_kg_findings
  ├── write_publication_as_finding()   — published candidate → bt_kg_findings
  ├── supersede_finding()              — temporal supersession
  ├── list_active_findings()           — query active findings
  └── list_shadow_findings()           — query shadow findings
```

## Data Flow

```
Upstream sources (findings, evidence_items)
    ↓
PaperIngestionWorker → bt_paper_segments (status: ingested → scored)
    ↓
EntityRelationExtractor → bt_kg_entities + bt_kg_relations (status: extracted)
    ↓
KGEvidenceSource.gather() → list[EvidenceItem] (shadow retrieval)
    ↓
RetrievalComparisonHarness → comparison artifacts (JSON/MD/CSV)

Published candidates → kg_writer → bt_kg_findings (shadow write-back)
```

## Embedding Regime

- All KG embeddings use Regime 2: qwen3-embedding:4b (2560d)
- bt_paper_segments.embedding_json stores segment embeddings
- No mixing with upstream 768d paper_embeddings
- MockEmbeddingProvider used for offline tests

## Entity Types

material, compound, mechanism, process, property, organism, gene, protein,
device, method, concept, metric, phenomenon, structure, technology

## Relation Types

causes, inhibits, enhances, composed_of, measured_by, used_in, produces,
degrades, catalyzes, related_to, enables, requires, competes_with, analog_of

## Throughput Safety

- All LLM calls are sequential (no parallelism)
- Extraction processes segments one at a time
- Compression is optional and bounded
- No uncontrolled parallelism
