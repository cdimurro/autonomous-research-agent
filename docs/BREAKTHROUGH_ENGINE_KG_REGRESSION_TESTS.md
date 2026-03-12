# KG Regression Tests — Phase 10A

## Test File

`tests/test_breakthrough/test_phase10a.py` — 57 offline-safe tests

## Test Coverage

### A: Migration 12 — bt_paper_segments (5 tests)
- Table existence
- Insert and read
- Count with filters
- Status update
- Filter by status

### B: Migration 12 — bt_kg_entities (3 tests)
- Table existence
- Insert and read
- Entities for segment query

### C: Migration 12 — bt_kg_relations (3 tests)
- Table existence
- Insert and read
- Relations for entity query

### D: Migration 12 — bt_kg_findings (3 tests)
- Table existence
- Insert and read
- Temporal fields (valid_from, valid_until, superseded_by)

### E: Paper Ingestion (6 tests)
- segment_text basic splitting
- segment_text empty input
- segment_text long text hard-splitting
- Relevance scorer with mock embeddings
- Batch relevance scoring
- Ingestion from evidence items

### F: KG Extraction (10 tests)
- Mock extractor returns entities
- Mock extractor returns relations
- Entity types valid
- Relation types valid
- Full extraction pipeline with mock
- Segment status marked as extracted
- Short text segments skipped
- JSON response parsing (valid)
- JSON response parsing (code block)
- JSON response parsing (invalid)

### G: KG Shadow Retrieval (5 tests)
- Implements EvidenceSource ABC
- gather() returns EvidenceItem list
- Respects min_relevance threshold
- Graph context retrieval
- EvidenceItem shape validation

### H: Comparison Harness (7 tests)
- Compute metrics
- Compute metrics (empty)
- Compute overlap
- Full harness comparison run
- Export JSON
- Export Markdown
- Export CSV

### I: KG Write-Back (5 tests)
- Write candidate as finding
- Write publication as finding
- Supersede finding
- List active findings
- List shadow findings

### J: Embedding Regime Protection (3 tests)
- Mock provider dimension
- Ollama provider default 2560d
- Segment scorer uses provider dimension

### K: Schema Version (1 test)
- Schema version >= 12

### L: Production Pipeline Untouched (4 tests)
- Orchestrator has no KG imports
- Daily search has no KG imports
- EvidenceSource ABC unchanged
- CompositeRetrievalSource still exists

### M: CLI Integration (2 tests)
- Ingest parser exists
- KG parser exists

## Running Tests

```bash
# Phase 10A tests only
PYTHONPATH=/Users/openclaw/breakthrough-engine .venv/bin/pytest tests/test_breakthrough/test_phase10a.py -v

# Full suite
PYTHONPATH=/Users/openclaw/breakthrough-engine .venv/bin/pytest tests/test_breakthrough/ -v
```
