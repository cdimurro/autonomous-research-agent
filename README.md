# 24/7 Autonomous Research Agent

A fully autonomous, local-first research agent that runs 24/7. It continuously ingests scientific papers, parses PDFs, extracts structured findings with provenance, builds a knowledge graph, and generates novel cross-domain hypotheses — all running on your own hardware with no cloud dependency.

**Configure it for any field or research domain** — energy, biology, medicine, materials science, computer science, or anything else. Just add your own RSS feeds and APIs.

## Features

- **Domain-agnostic**: Configure feeds, APIs, and validators for any field or research domain
- **Fully local**: Runs on a single machine with Ollama (local LLM), no API keys needed
- **9-phase pipeline**: Ingest → Fetch → Parse → Extract → Judge → Feedback → Align → Index → Hypothesize
- **Provenance-first**: Every extracted finding includes a verbatim quote from the source text
- **Hallucination detection**: Deterministic validators + quote verification catch fabricated data
- **Knowledge graph**: Entities, relations, and communities stored in SQLite with vector search
- **Hypothesis generation**: Cross-domain synthesis with recursive critique
- **Thermal safety**: Monitors system temperature, pauses on overheating
- **Kill switch**: Create a single file to halt all processing instantly

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    launchd (macOS)                       │
│  Orchestrator (4h)  Digest (7am)  Backup (2am)  API     │
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
│  11 tables + 3 vector tables                            │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Prerequisites

- **macOS** (Apple Silicon recommended) or Linux
- **Python 3.11+**
- **Ollama** — [install](https://ollama.ai)
- **Docker** — for GROBID PDF parser
- **Poppler** — `brew install poppler` (provides `pdftotext`, `pdffonts`)

### 2. Install

```bash
# Clone the repo
git clone https://github.com/cdimurro/autonomous-research-agent.git
cd autonomous-research-agent

# Create Python virtual environment
python3.11 -m venv ~/research-venv
source ~/research-venv/bin/activate
pip install -r requirements.txt

# Pull an Ollama model
ollama pull qwen3.5:9b-q4_K_M
# QWEN 3.5 9B-q4_K_M is recommended for running 24/7 a Mac Mini with 16GB
# Adjust the AI model for your hardware

# Start GROBID
docker pull lfoppiano/grobid:0.8.2
docker run -d --name grobid -p 8070:8070 --memory=1280m lfoppiano/grobid:0.8.2

# Download SPECTER2 weights (for scientific embeddings)
python3 -c "
from transformers import AutoTokenizer
from adapters import AutoAdapterModel
tokenizer = AutoTokenizer.from_pretrained('allenai/specter2_base')
model = AutoAdapterModel.from_pretrained('allenai/specter2_base')
model.load_adapter('allenai/specter2', source='hf', load_as='proximity', set_active=True)
print('SPECTER2 downloaded successfully')
"
```

### 3. Configure

```bash
# Set up environment
cp .env.example .env
# Edit .env — set paths for your system

# Initialize the database
bash scripts/db-init.sh

# Create runtime directories
mkdir -p runtime/{db,pdfs,parsed,extractions,logs,state,backups,workspace,cache}
```

### 4. Add Your Research Domain

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

  openalex_ml:
    url: "https://api.openalex.org/works"
    type: api
    poll_interval_hours: 12
    params:
      filter: "concepts.id:C154945302,from_publication_date:{today-7d}"
      sort: "publication_date:desc"
      per_page: 50
```

Optionally add domain ontologies in `config/ontologies.yaml` and numeric validators in `config/validators.yaml`.

### 5. Run

```bash
# Run a single cycle
source .env
bash scripts/orchestrator.sh --cycle

# Or run individual phases
bash scripts/orchestrator.sh --phase ingest
bash scripts/orchestrator.sh --phase fetch
bash scripts/orchestrator.sh --phase extract
```

### 6. Query Results

```bash
# Start the API
python3 scripts/query-endpoint.py &

# Query papers
curl "localhost:8099/papers?status=indexed&limit=10"

# Search findings
curl "localhost:8099/findings?min_confidence=0.7"

# Semantic search
curl "localhost:8099/search?q=transformer+architecture&type=vector"

# View hypotheses
curl "localhost:8099/hypotheses?status=proposed"

# System stats
curl "localhost:8099/stats"
```

### 7. Run Autonomously (macOS)

Edit the launchd plists in `launchd/` — replace `/PATH/TO/REPO` and `/PATH/TO/VENV` with your actual paths, then:

```bash
cp launchd/*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.scires.orchestrator.plist
launchctl load ~/Library/LaunchAgents/com.scires.query-endpoint.plist
launchctl load ~/Library/LaunchAgents/com.scires.daily-digest.plist
launchctl load ~/Library/LaunchAgents/com.scires.db-backup.plist
```

The agent will now run every 4 hours, generate daily digests at 07:00, and back up the database at 02:00.

## The Pipeline in Detail

| Phase | What It Does |
|-------|-------------|
| **INGEST** | Polls RSS/API feeds, filters by keyword relevance, deduplicates by arXiv ID / DOI / PDF hash |
| **FETCH** | Downloads PDFs via multi-source resolution chain: direct URL → Unpaywall → Semantic Scholar → OpenAlex |
| **PARSE** | Tiered parser routing: GROBID for metadata (always), Docling for full text, Docling+OCR for scanned PDFs |
| **EXTRACT** | Local LLM extracts structured findings, entities, and relations with verbatim provenance quotes |
| **JUDGE** | Hallucination check (quote exists in text?), numeric validation against physical bounds, confidence scoring |
| **FEEDBACK** | Low-confidence papers get critique-and-re-extract loops (up to 3 cycles) |
| **ALIGN** | Maps entities to configured ontologies (optional — skips if no ontologies defined) |
| **INDEX** | SPECTER2 embeddings stored in sqlite-vec for semantic similarity search |
| **HYPOTHESIZE** | Cross-finding synthesis with mandatory contradiction checking and recursive critique |

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Environment variables (paths, model, ports) |
| `config/sources.yaml` | RSS feeds and API endpoints for your research domain |
| `config/ontologies.yaml` | Domain ontology mappings (ENVO, BDF, GO, custom) |
| `config/validators.yaml` | Numeric range validators for your domain's metrics |
| `config/models.yaml` | LLM model configuration and task routing |
| `config/confidence.yaml` | Confidence scoring weights and thresholds |
| `config/routing.yaml` | PDF parser tier routing rules |

## Database Schema

SQLite with WAL mode, foreign keys, and sqlite-vec extension:

| Table | Contents |
|-------|----------|
| `papers` | Metadata, status state machine, relevance scores |
| `findings` | Structured findings with provenance quotes and confidence |
| `entities` | Named entities (materials, methods, organisms, etc.) |
| `relations` | Typed relationships (uses, measures, contradicts, etc.) |
| `hypotheses` | Generated hypotheses with critique logs |
| `confidence_scores` | Per-finding confidence breakdowns |
| `verification_results` | Deterministic validator outputs |
| `extraction_provenance` | Parser used, tier, quality score, timing |
| `feed_state` | Per-feed polling state |
| `graph_communities` | Detected entity clusters |
| `paper_embeddings` | SPECTER2 768-dim vectors for semantic search |

## Project Structure

```
├── .env.example                    # Environment template
├── config/
│   ├── sources.yaml                # Feed definitions (YOU EDIT THIS)
│   ├── ontologies.yaml             # Domain ontologies (optional)
│   ├── validators.yaml             # Numeric validators (optional)
│   ├── models.yaml                 # LLM configuration
│   ├── confidence.yaml             # Scoring weights
│   └── routing.yaml                # Parser routing rules
├── prompts/
│   ├── system_extractor.md         # Extraction prompt
│   ├── system_judge.md             # Hallucination detection
│   ├── system_alignment.md         # Ontology mapping
│   └── system_hypothesis.md        # Hypothesis generation
├── scripts/
│   ├── orchestrator.sh             # Main 9-phase loop
│   ├── feed-ingest.sh              # RSS/API polling
│   ├── pdf-fetch.sh                # Multi-source PDF download
│   ├── parser-route.sh             # Tiered parser routing
│   ├── structsense-extract.sh      # LLM extraction
│   ├── judge-score.sh              # Confidence scoring
│   ├── feedback-loop.sh            # Critique loop
│   ├── ontology-align.sh           # Entity alignment
│   ├── embed-index.sh              # SPECTER2 indexing
│   ├── hypothesis-gen.sh           # Hypothesis generation
│   ├── query-endpoint.py           # Flask API
│   ├── db-init.sh                  # Schema setup
│   ├── db-backup.sh                # Daily backups
│   ├── health-check.sh             # System monitoring
│   └── lib/                        # Shared utilities
├── launchd/                        # macOS scheduling (edit paths)
├── tests/                          # Test suite
└── runtime/                        # All mutable data (gitignored)
```

## Safety

- **Kill switch**: `echo '{}' > runtime/state/STOPPED.json` halts processing. Remove to resume.
- **Thermal guard**: Pauses on high CPU temperature (macOS `kern.thermalpressure`)
- **Provenance**: Every finding must cite a verbatim quote from the source
- **Deterministic validation**: Numeric values checked against physical bounds (no LLM)
- **Daily backups**: Compressed SQLite backups with 14-day rotation
- **Auto-retry**: Failed papers retry up to 3 times across cycles

## Tests

```bash
bash tests/test-schema-validation.sh   # Database schema integrity
bash tests/test-validators.sh          # Numeric validators
bash tests/test-parser-routing.sh      # PDF parser tools
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

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Domain config packs are especially welcome!
