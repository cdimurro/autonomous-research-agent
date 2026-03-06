# Changelog

## 1.0.0 — Initial Public Release

### Core Pipeline
- 9-phase autonomous pipeline: ingest, fetch, parse, extract, judge, feedback, align, index, hypothesize
- Tiered PDF parsing (GROBID + Docling) with automatic quality-based routing
- Local LLM extraction via Ollama with provenance-first structured output
- Knowledge graph with entity resolution and community detection
- SPECTER2 embeddings for semantic similarity search (sqlite-vec)
- Hypothesis generation with mandatory contradiction checking

### Scientific Evaluation
- Two-layer evaluation architecture: confidence scoring + rubric grading
- 5-factor confidence scoring with configurable weights and thresholds
- Deterministic rubric grading: 7 criteria, 10 points, no LLM in the evaluation path
- Domain-specific numeric validators (energy, materials, ecology, generic)
- Hallucination detection via provenance quote verification
- Explicit artifact contracts (JSON Schema) for conclusion candidates and rubric results

### Infrastructure
- SQLite with WAL mode, 12 tables + 3 vector tables
- launchd scheduling for autonomous 24/7 operation (macOS)
- Flask API for querying papers, findings, hypotheses, and semantic search
- Daily backups with 14-day rotation
- Kill switch and thermal safety guard

### Testing
- 4 test suites: schema validation, numeric validators, rubric grading, parser routing
- 85 total test cases
- CI via GitHub Actions (macOS)

### Configuration
- Domain-agnostic: feeds, validators, ontologies, and rubrics defined in YAML
- No code changes needed to add a new research domain
