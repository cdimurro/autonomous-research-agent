# Autonomous Research Agent

[![CI](https://github.com/cdimurro/autonomous-research-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/cdimurro/autonomous-research-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An autonomous agent that ingests scientific papers, extracts structured findings backed by verbatim source quotes, validates every claim against physical bounds, and scores each conclusion through a 7-criterion rubric. Runs 24/7 on your own hardware with no cloud dependency.

Configure it for any research domain — just add your feeds, validators, and ontologies.

## What Makes This Different

Most research tools stop at text extraction. This system goes further: every finding must carry a verbatim quote from the source paper, every numeric value is checked against known physical limits, and every conclusion is graded across seven independent criteria before it enters the knowledge graph.

The LLM handles extraction. Everything after that — numeric validation, quote verification, rubric grading — is deterministic. No LLM in the evaluation path.

```
Paper → Parsed text → Extracted finding → Provenance quote
  → Numeric validation → Confidence score → Rubric grade
    → Per-criterion pass/fail with rationale
```

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

## Evaluation

Each finding passes through two independent evaluation layers:

**Layer 1 — Confidence scoring** (`judge-score.sh`): A weighted score from five factors — source quality, extraction quality, numeric validation, hallucination detection, and cross-reference. Scores above 0.60 are accepted, below 0.25 are rejected.

**Layer 2 — Rubric grading** (`rubric-grade.sh`): Seven criteria, each scored independently with its own pass/fail and rationale. Defined in [`config/rubrics.yaml`](config/rubrics.yaml). All grading logic is deterministic.

| Criterion | What It Checks | Points |
|---|---|---|
| Evidence support | Finding has a metric and a value | 2 |
| Provenance support | Verbatim quote from the source paper | 2 |
| Numeric consistency | Values within known physical limits | 2 |
| Unit consistency | Reported units match expected units | 1 |
| Contradiction awareness | Text doesn't contradict its own data | 1 |
| Uncertainty calibration | High confidence backed by strong evidence | 1 |
| Conclusion alignment | Text references the metric it claims to report | 1 |

**Pass threshold**: 6/10. Results are stored in the `rubric_results` table and written as JSON to `runtime/evaluations/`.

See [`docs/EVALUATION.md`](docs/EVALUATION.md) for the full evaluation flow and extension guide.

## End-to-End Example

See the rubric in action — grades two findings (one strong, one weak) without needing Ollama or GROBID:

```bash
bash examples/demo-rubric-eval.sh
```

Output shows each criterion's score and reasoning. See [`examples/expected-output/`](examples/expected-output/) for sample results.

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

# Python environment
python3.11 -m venv ~/research-venv
source ~/research-venv/bin/activate
pip install -r requirements.txt

# LLM (9B recommended for 16GB systems)
ollama pull qwen3.5:9b-q4_K_M

# GROBID PDF parser
docker pull lfoppiano/grobid:0.8.2
docker run -d --name grobid -p 8070:8070 --memory=2048m lfoppiano/grobid:0.8.2

# SPECTER2 scientific embeddings
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

Edit `config/sources.yaml` to add feeds for your field:

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

Add numeric validators in `config/validators.yaml` and ontology mappings in `config/ontologies.yaml`.

### Run

```bash
source .env

# Full pipeline cycle
bash scripts/orchestrator.sh --cycle

# Individual phases
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
| **INGEST** | Polls RSS/API feeds, filters by keywords, deduplicates by arXiv ID / DOI / PDF hash |
| **FETCH** | Downloads PDFs via direct URL → Unpaywall → Semantic Scholar → OpenAlex |
| **PARSE** | GROBID for metadata, Docling for full text, OCR for scanned PDFs |
| **EXTRACT** | LLM extracts findings, entities, and relations with verbatim source quotes |
| **JUDGE** | Numeric validation, quote verification, confidence scoring, rubric grading |
| **FEEDBACK** | Low-confidence findings get re-extracted (up to 3 cycles) |
| **ALIGN** | Maps entities to configured ontologies |
| **INDEX** | SPECTER2 embeddings for semantic similarity search |
| **HYPOTHESIZE** | Cross-finding synthesis with contradiction checking |

## Configuration

| File | Purpose |
|------|---------|
| `config/sources.yaml` | RSS feeds and API endpoints |
| `config/validators.yaml` | Numeric range validators for your domain |
| `config/ontologies.yaml` | Domain ontology mappings |
| `config/confidence.yaml` | Confidence scoring weights and thresholds |
| `config/rubrics.yaml` | Rubric definitions for evaluation |
| `config/models.yaml` | LLM model configuration |
| `config/routing.yaml` | PDF parser routing rules |
| `config/skills.yaml` | Script capabilities and network policy |

## Database

SQLite with WAL mode, foreign keys, and sqlite-vec:

| Table | Contents |
|-------|----------|
| `papers` | Metadata, processing status, relevance scores |
| `findings` | Structured findings with provenance quotes and confidence |
| `entities` | Named entities (materials, methods, organisms, etc.) |
| `relations` | Typed relationships (uses, measures, contradicts, etc.) |
| `hypotheses` | Generated hypotheses with critique logs |
| `confidence_scores` | Per-finding confidence factor breakdowns |
| `verification_results` | Validator outputs |
| `rubric_results` | Per-finding rubric grades with item-level detail |
| `extraction_provenance` | Parser used, tier, quality score, timing |
| `feed_state` | Per-feed polling state |
| `graph_communities` | Entity clusters |
| `paper_embeddings` | SPECTER2 768-dim vectors (sqlite-vec) |

## Project Structure

```
├── config/                        # All configuration (YAML)
│   ├── sources.yaml               # Feed definitions (start here)
│   ├── validators.yaml            # Numeric range validators
│   ├── rubrics.yaml               # Evaluation rubric
│   ├── confidence.yaml            # Scoring weights
│   ├── ontologies.yaml            # Domain ontologies
│   ├── models.yaml                # LLM configuration
│   ├── routing.yaml               # Parser routing
│   └── skills.yaml                # Script capabilities
├── schemas/                       # Artifact contracts (JSON Schema)
│   ├── scientific_conclusion_candidate.json
│   ├── rubric_result.json
│   └── rubric_item_result.json
├── scripts/
│   ├── orchestrator.sh            # 9-phase pipeline
│   ├── judge-score.sh             # Confidence scoring + rubric dispatch
│   ├── rubric-grade.sh            # Rubric evaluation
│   ├── feed-ingest.sh             # Feed polling
│   ├── pdf-fetch.sh               # PDF downloads
│   ├── parser-route.sh            # Parser routing
│   ├── structsense-extract.sh     # LLM extraction
│   ├── feedback-loop.sh           # Re-extraction loop
│   ├── ontology-align.sh          # Ontology mapping
│   ├── embed-index.sh             # Embedding indexing
│   ├── hypothesis-gen.sh          # Hypothesis generation
│   ├── query-endpoint.py          # Flask API
│   ├── db-init.sh                 # Schema setup
│   ├── db-backup.sh               # Daily backups
│   ├── health-check.sh            # Monitoring
│   └── lib/                       # Shared utilities
├── prompts/                       # LLM system prompts
├── examples/                      # End-to-end demo
├── docs/                          # Architecture docs
├── launchd/                       # macOS scheduling
├── tests/                         # Test suite
└── runtime/                       # All mutable data (gitignored)
```

## Design Principles

1. **No finding without proof.** Every claim must cite a verbatim quote from the source text.
2. **LLM reads, logic validates.** Numeric checks, unit checks, and rubric grading are deterministic.
3. **Everything is inspectable.** JSON schemas, structured outputs, typed database columns.
4. **Config over code.** New domains, validators, and rubrics go in YAML — no script changes needed.
5. **Phases stand alone.** Each pipeline step reads from and writes to the database independently.

## Non-Goals

- **Not a platform.** No plugins, no SDK. Extend by editing config or scripts.
- **Not a peer review replacement.** The rubric checks extraction quality, not scientific truth.
- **Not cloud-dependent.** One machine, SQLite, local LLM.
- **Not built for scale.** Built for thoroughness on one researcher's hardware.

## Safety

- **Kill switch**: `echo '{}' > runtime/state/STOPPED.json` stops all processing
- **Thermal guard**: Pauses on high CPU temperature (macOS)
- **Provenance enforcement**: Findings without source quotes are flagged
- **Range validation**: Numeric values checked against physical bounds
- **Daily backups**: Compressed SQLite snapshots, 14-day rotation
- **Auto-retry**: Failed papers retry up to 3 times

## Tests

```bash
bash tests/test-schema-validation.sh   # Database schema (17 checks)
bash tests/test-validators.sh          # Numeric validators (39 cases)
bash tests/test-rubric-grading.sh      # Rubric grading (29 cases)
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

Phases run serially — heavy components never overlap. Ollama unloads after 2 minutes idle.

## License

MIT — see [LICENSE](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
