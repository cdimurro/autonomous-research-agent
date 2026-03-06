# Autonomous Research Agent

[![CI](https://github.com/cdimurro/autonomous-research-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/cdimurro/autonomous-research-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A provenance-first scientific reasoning engine that runs autonomously on your own hardware. It ingests papers from any research domain, extracts structured findings with verbatim source evidence, validates claims against physical bounds, and evaluates every conclusion through a decomposed rubric — producing machine-readable audit trails at each step.

No cloud dependency. No API keys. Every extracted claim carries its own proof.

## What Makes This Different

Most research tools extract text. This system extracts *accountable scientific claims*.

Every finding must carry a verbatim provenance quote from the source paper. Numeric values are checked against domain-specific physical bounds (you can't claim 99% solar cell efficiency — the validator knows the theoretical limit is 47%). Conclusions are then graded against a 7-criterion rubric that scores evidence quality, provenance strength, numeric consistency, and calibration — independently and deterministically.

The result is a knowledge graph where every node has an auditable evidence chain:

```
Paper → Parsed text → Extracted finding → Provenance quote
  → Numeric validation → Confidence score → Rubric grade
    → Per-criterion pass/fail with rationale
```

This isn't an LLM wrapper. It's a structured evaluation architecture that uses an LLM for extraction, then validates everything the LLM said.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    launchd (macOS)                       │
│  Orchestrator (1h)  Digest (7am)  Backup (2am)  API     │
└──────────┬──────────────┬────────────┬───────────┬──────┘
           │              │            │           │
           ▼              │            │           ▼
┌──────────────────────┐  │            │  ┌──────────────┐
│  9-Phase Pipeline    │  │            │  │ Flask API    │
│                      │  │            │  │ localhost    │
│  1. INGEST (feeds)   │  │            │  │ :8099        │
│  2. FETCH  (PDFs)    │  │            │  └──────┬───────┘
│  3. PARSE  (tiered)  │  │            │         │
│  4. EXTRACT (LLM)    │  │            │         │
│  5. JUDGE  (validate)│  │            │         │
│  5b.FEEDBACK (retry) │  │            │         │
│  6. ALIGN  (ontology)│  │            │         │
│  7. INDEX  (vectors) │  │            │         │
│  8. HYPOTHESIZE      │  │            │         │
└──────────┬───────────┘  │            │         │
           │              │            │         │
           ▼              ▼            ▼         ▼
┌─────────────────────────────────────────────────────────┐
│                 runtime/db/scires.db                     │
│  SQLite (WAL) + sqlite-vec (SPECTER2 768-dim vectors)   │
│  12 tables + 3 vector tables                            │
└─────────────────────────────────────────────────────────┘
```

## Evaluation Architecture

Scientific claims pass through two independent evaluation layers:

**Layer 1 — Confidence scoring** (`judge-score.sh`): A weighted composite of five factors — source quality, extraction quality, numeric validation, hallucination detection, and cross-reference corroboration. Produces a 0–1 score and an accept/revise/reject verdict. Purely deterministic except for the hallucination check (fuzzy quote matching).

**Layer 2 — Rubric grading** (`rubric-grade.sh`): Decomposes evaluation into 7 independently-scored criteria defined in [`config/rubrics.yaml`](config/rubrics.yaml). Each criterion produces a score, pass/fail status, failure tags, and a human-readable rationale. All grading logic is deterministic — no LLM involvement.

| Rubric Criterion | What It Checks | Points |
|---|---|---|
| Evidence support | Structured data has metric + value | 2 |
| Provenance support | Verbatim source quote present and substantial | 2 |
| Numeric consistency | Values pass domain-specific range validators | 2 |
| Unit consistency | Reported units match expected units for the metric | 1 |
| Contradiction awareness | Content doesn't contradict its own structured data | 1 |
| Uncertainty calibration | High confidence requires strong underlying evidence | 1 |
| Conclusion alignment | Textual content references the structured metric/value | 1 |

**Pass threshold**: 6/10. Results are persisted to the `rubric_results` table and written as JSON artifacts to `runtime/evaluations/`.

See [`docs/EVALUATION.md`](docs/EVALUATION.md) for the full evaluation flow, artifact contracts, and extension guide.

## End-to-End Example

See what the evaluation pipeline actually produces. From a fresh clone:

```bash
# After setup (see Quick Start below), run the demo:
bash examples/demo-rubric-eval.sh
```

This grades two realistic scientific conclusion candidates — one strong, one weak — and writes rubric results to `examples/expected-output/`. You can inspect the results to see exactly how the 7-criterion rubric evaluates each claim.

See [`examples/`](examples/) for the full demo, input fixtures, and expected output.

## Quick Start

### Prerequisites

- **macOS** (Apple Silicon recommended) or Linux
- **Python 3.11+**
- **Ollama** — [install](https://ollama.ai)
- **Docker** — for GROBID PDF parser
- **Poppler** — `brew install poppler` (provides `pdftotext`, `pdffonts`)

### Install

```bash
git clone https://github.com/cdimurro/autonomous-research-agent.git
cd autonomous-research-agent

# Create Python virtual environment
python3.11 -m venv ~/research-venv
source ~/research-venv/bin/activate
pip install -r requirements.txt

# Pull an Ollama model (9B recommended for 16GB systems)
ollama pull qwen3.5:9b-q4_K_M

# Start GROBID
docker pull lfoppiano/grobid:0.8.2
docker run -d --name grobid -p 8070:8070 --memory=2048m lfoppiano/grobid:0.8.2

# Download SPECTER2 weights (scientific embeddings)
python3 -c "
from transformers import AutoTokenizer
from adapters import AutoAdapterModel
tokenizer = AutoTokenizer.from_pretrained('allenai/specter2_base')
model = AutoAdapterModel.from_pretrained('allenai/specter2_base')
model.load_adapter('allenai/specter2', source='hf', load_as='proximity', set_active=True)
print('SPECTER2 downloaded successfully')
"
```

### Configure

```bash
cp .env.example .env
# Edit .env — set paths for your system

bash scripts/db-init.sh
mkdir -p runtime/{db,pdfs,parsed,extractions,evaluations,logs,state,backups,workspace,cache}
```

### Add Your Research Domain

Edit `config/sources.yaml` to add RSS feeds and API endpoints for your field:

```yaml
feeds:
  arxiv_cs_ai:
    url: "https://rss.arxiv.org/rss/cs.AI"
    type: rss
    poll_interval_hours: 4
    relevance_keywords:
      - "large language model"
      - "reinforcement learning"
```

Add domain-specific numeric validators in `config/validators.yaml` and ontology mappings in `config/ontologies.yaml`.

### Run

```bash
source .env

# Run a single pipeline cycle
bash scripts/orchestrator.sh --cycle

# Or run individual phases
bash scripts/orchestrator.sh --phase ingest
bash scripts/orchestrator.sh --phase fetch
bash scripts/orchestrator.sh --phase extract
```

### Query Results

```bash
python3 scripts/query-endpoint.py &

curl "localhost:8099/papers?status=indexed&limit=10"
curl "localhost:8099/findings?min_confidence=0.7"
curl "localhost:8099/search?q=transformer+architecture&type=vector"
curl "localhost:8099/hypotheses?status=proposed"
curl "localhost:8099/stats"
```

### Run Autonomously (macOS)

```bash
# Edit paths in launchd/*.plist, then:
cp launchd/*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.scires.orchestrator.plist
launchctl load ~/Library/LaunchAgents/com.scires.query-endpoint.plist
launchctl load ~/Library/LaunchAgents/com.scires.daily-digest.plist
launchctl load ~/Library/LaunchAgents/com.scires.db-backup.plist
```

## The Pipeline

| Phase | What It Does |
|-------|-------------|
| **INGEST** | Polls RSS/API feeds, filters by keyword relevance, deduplicates by arXiv ID / DOI / PDF hash |
| **FETCH** | Downloads PDFs via multi-source resolution: direct URL → Unpaywall → Semantic Scholar → OpenAlex |
| **PARSE** | Tiered parser routing: GROBID for metadata (always), Docling for full text, Docling+OCR for scanned PDFs |
| **EXTRACT** | Local LLM extracts structured findings, entities, and relations with verbatim provenance quotes |
| **JUDGE** | Deterministic validation (numeric bounds, quote verification, confidence scoring) + rubric grading |
| **FEEDBACK** | Low-confidence findings get critique-and-re-extract loops (up to 3 cycles) |
| **ALIGN** | Maps entities to configured ontologies (skips if none defined) |
| **INDEX** | SPECTER2 embeddings stored in sqlite-vec for semantic similarity search |
| **HYPOTHESIZE** | Cross-finding synthesis with mandatory contradiction checking and recursive critique |

## Configuration

| File | Purpose |
|------|---------|
| `config/sources.yaml` | RSS feeds and API endpoints for your research domain |
| `config/validators.yaml` | Numeric range validators for domain-specific metrics |
| `config/ontologies.yaml` | Domain ontology mappings (ENVO, BDF, GO, custom) |
| `config/confidence.yaml` | Confidence scoring weights and thresholds |
| `config/rubrics.yaml` | Rubric definitions for scientific evaluation |
| `config/models.yaml` | LLM model configuration and task routing |
| `config/routing.yaml` | PDF parser tier routing rules |
| `config/skills.yaml` | Script capability manifest (subcommands, network policy) |

## Database

SQLite with WAL mode, foreign keys, and sqlite-vec:

| Table | Contents |
|-------|----------|
| `papers` | Metadata, status state machine, relevance scores |
| `findings` | Structured findings with provenance quotes and confidence |
| `entities` | Named entities (materials, methods, organisms, etc.) |
| `relations` | Typed relationships (uses, measures, contradicts, etc.) |
| `hypotheses` | Generated hypotheses with critique logs |
| `confidence_scores` | Per-finding confidence breakdowns |
| `verification_results` | Deterministic validator outputs |
| `rubric_results` | Per-finding rubric grading with item-level detail |
| `extraction_provenance` | Parser used, tier, quality score, timing |
| `feed_state` | Per-feed polling state |
| `graph_communities` | Detected entity clusters |
| `paper_embeddings` | SPECTER2 768-dim vectors (sqlite-vec) |

## Project Structure

```
├── config/                        # All configuration (YAML)
│   ├── sources.yaml               # Feed definitions (YOU EDIT THIS)
│   ├── validators.yaml            # Numeric range validators
│   ├── rubrics.yaml               # Evaluation rubric definitions
│   ├── confidence.yaml            # Scoring weights
│   ├── ontologies.yaml            # Domain ontologies
│   ├── models.yaml                # LLM configuration
│   ├── routing.yaml               # Parser routing rules
│   └── skills.yaml                # Script capability manifest
├── schemas/                       # Artifact contracts (JSON Schema)
│   ├── scientific_conclusion_candidate.json
│   ├── rubric_result.json
│   └── rubric_item_result.json
├── scripts/
│   ├── orchestrator.sh            # 9-phase pipeline loop
│   ├── judge-score.sh             # Confidence scoring + rubric dispatch
│   ├── rubric-grade.sh            # Rubric evaluation engine
│   ├── feed-ingest.sh             # RSS/API polling
│   ├── pdf-fetch.sh               # Multi-source PDF download
│   ├── parser-route.sh            # Tiered parser routing
│   ├── structsense-extract.sh     # LLM extraction
│   ├── feedback-loop.sh           # Critique loop
│   ├── ontology-align.sh          # Entity alignment
│   ├── embed-index.sh             # SPECTER2 indexing
│   ├── hypothesis-gen.sh          # Hypothesis generation
│   ├── query-endpoint.py          # Flask API
│   ├── db-init.sh                 # Schema setup
│   ├── db-backup.sh               # Daily backups
│   ├── health-check.sh            # System monitoring
│   └── lib/                       # Shared utilities
├── prompts/                       # LLM system prompts
├── examples/                      # End-to-end demo
├── docs/                          # Architecture documentation
├── launchd/                       # macOS scheduling
├── tests/                         # Test suite
└── runtime/                       # All mutable data (gitignored)
```

## Design Principles

1. **Provenance is mandatory.** Every extracted claim must cite a verbatim quote from the source text. No quote, no finding.
2. **Validation is deterministic.** Numeric bounds, unit checks, and rubric grading use pure logic — no LLM in the evaluation path.
3. **Artifacts are machine-readable.** Schemas in `schemas/`, structured JSON outputs, typed database columns. Everything is inspectable.
4. **Configuration over code.** New domains, validators, ontologies, and rubrics are added through YAML, not by modifying scripts.
5. **Phases are independent.** Each pipeline phase reads from and writes to the database. Phases can run individually, be skipped, or be replaced.

## Non-Goals

This project intentionally does not:

- **Build a platform.** No plugin system, no SDK, no extension API. Add capabilities by editing config or scripts.
- **Replace peer review.** The rubric evaluates extraction quality and evidence support, not scientific truth.
- **Require cloud infrastructure.** Everything runs on a single machine with SQLite and a local LLM.
- **Optimize for scale.** Designed for thoroughness on a single researcher's hardware, not for processing millions of papers.

## Safety

- **Kill switch**: `echo '{}' > runtime/state/STOPPED.json` halts all processing instantly
- **Thermal guard**: Pauses on high CPU temperature (macOS `kern.thermalpressure`)
- **Provenance enforcement**: Findings without source quotes are flagged
- **Deterministic validation**: Numeric values checked against physical bounds without LLM involvement
- **Daily backups**: Compressed SQLite backups with 14-day rotation
- **Auto-retry**: Failed papers retry up to 3 times across cycles

## Tests

```bash
bash tests/test-schema-validation.sh   # Database schema integrity (17 checks)
bash tests/test-validators.sh          # Numeric validators (39 cases)
bash tests/test-rubric-grading.sh      # Rubric config + grading logic (29 cases)
bash tests/test-parser-routing.sh      # PDF parser tools (requires poppler)
```

## RAM Budget (16 GB system)

| Component | Steady | Peak |
|-----------|--------|------|
| OS | 2.0 GB | 2.5 GB |
| Ollama (9B Q4_K_M) | 5.8 GB | 6.2 GB |
| GROBID (Docker) | 0.8 GB | 1.2 GB |
| Docling (on-demand) | 0.3 GB | 0.8 GB |
| SPECTER2 (on-demand) | 0.4 GB | 0.6 GB |
| Flask API | 0.05 GB | 0.1 GB |
| **Total** | **~9.5 GB** | **~11.4 GB** |

Phases run serially — heavy components never overlap at peak. Ollama auto-unloads after 2 minutes idle.

## License

MIT — see [LICENSE](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
