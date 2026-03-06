# Autonomous Research Agent

[![CI](https://github.com/cdimurro/autonomous-research-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/cdimurro/autonomous-research-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

This agent reads scientific papers, pulls out the findings, and checks whether the LLM made things up. It runs 24/7 on your own machine — no cloud, no API keys.

Point it at any research domain. It fetches papers from RSS feeds and APIs, parses the PDFs, extracts structured claims with exact quotes from the source text, then validates every number against known physical limits. A 7-point rubric grades each conclusion before it enters the knowledge graph.

The LLM does the reading. Everything after that is deterministic.

## Why This Exists

LLMs are good at pulling structured data out of papers. They're also good at making things up. This system treats the LLM as an untrusted source and checks its work:

- Every finding must include a verbatim quote from the paper. No quote, no finding.
- Numeric values get checked against physical bounds. Claim 99% solar cell efficiency? The validator knows the limit is 47%.
- A rubric scores each conclusion across 7 criteria — evidence, provenance, numeric consistency, units, contradictions, calibration, and alignment. All scoring is pure logic, no LLM.

The result: a knowledge graph where you can trace any claim back to the exact sentence in the paper that supports it.

```
Paper → Parsed text → Finding + quote from source
  → Numeric check → Confidence score → Rubric grade
    → Per-criterion pass/fail with explanation
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

## How Evaluation Works

Each finding goes through two checks.

**First: confidence scoring** (`judge-score.sh`). Five weighted factors — journal quality, extraction completeness, numeric validation, quote verification, and cross-reference — produce a 0–1 score. Above 0.60 is accepted, below 0.25 is rejected, everything else gets flagged for review.

**Then: rubric grading** (`rubric-grade.sh`). Each accepted finding is scored against 7 criteria. Every criterion is graded independently with its own pass/fail, score, and written explanation.

| Criterion | What it checks | Points |
|---|---|---|
| Evidence support | Does the finding have a metric and a value? | 2 |
| Provenance support | Is there a real quote from the paper? | 2 |
| Numeric consistency | Do the numbers fall within known physical limits? | 2 |
| Unit consistency | Do the units match what's expected for that metric? | 1 |
| Contradiction awareness | Does the text contradict its own data? | 1 |
| Uncertainty calibration | Is high confidence backed by strong evidence? | 1 |
| Conclusion alignment | Does the text actually mention the metric it claims to report? | 1 |

A finding needs 6/10 to pass. Results go into the database and get written as JSON files you can inspect.

See [`docs/EVALUATION.md`](docs/EVALUATION.md) for the full details.

## Try It

Run the demo to see the rubric in action. It grades two findings — one solid, one empty — without needing Ollama or GROBID:

```bash
bash examples/demo-rubric-eval.sh
```

Output shows each criterion's score and reasoning. Check [`examples/expected-output/`](examples/expected-output/) for what to expect.

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

python3.11 -m venv ~/research-venv
source ~/research-venv/bin/activate
pip install -r requirements.txt

# Pull a model (9B recommended for 16GB systems)
ollama pull qwen3.5:9b-q4_K_M

# Start GROBID
docker pull lfoppiano/grobid:0.8.2
docker run -d --name grobid -p 8070:8070 --memory=2048m lfoppiano/grobid:0.8.2

# Download SPECTER2 (scientific embeddings)
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

### Point It at Your Field

Edit `config/sources.yaml`:

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

You can also add numeric validators for your domain's metrics (`config/validators.yaml`) and ontology mappings (`config/ontologies.yaml`).

### Run

```bash
source .env

# Run one full cycle
bash scripts/orchestrator.sh --cycle

# Or run phases individually
bash scripts/orchestrator.sh --phase ingest
bash scripts/orchestrator.sh --phase fetch
bash scripts/orchestrator.sh --phase extract
```

### Query

```bash
python3 scripts/query-endpoint.py &

curl "localhost:8099/papers?status=indexed&limit=10"
curl "localhost:8099/findings?min_confidence=0.7"
curl "localhost:8099/search?q=transformer+architecture&type=vector"
curl "localhost:8099/hypotheses?status=proposed"
curl "localhost:8099/stats"
```

### Run 24/7 (macOS)

```bash
# Edit paths in launchd/*.plist, then:
cp launchd/*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.scires.orchestrator.plist
launchctl load ~/Library/LaunchAgents/com.scires.query-endpoint.plist
launchctl load ~/Library/LaunchAgents/com.scires.daily-digest.plist
launchctl load ~/Library/LaunchAgents/com.scires.db-backup.plist
```

## Pipeline

| Phase | What happens |
|-------|-------------|
| **INGEST** | Polls feeds, filters by keywords, deduplicates by arXiv ID / DOI / PDF hash |
| **FETCH** | Downloads PDFs — tries direct URL, then Unpaywall, Semantic Scholar, OpenAlex |
| **PARSE** | GROBID handles metadata, Docling handles full text, OCR kicks in for scanned pages |
| **EXTRACT** | LLM pulls out findings, entities, and relations — each with a verbatim source quote |
| **JUDGE** | Checks numbers against physical bounds, verifies quotes exist in the text, scores confidence, runs rubric |
| **FEEDBACK** | Low-confidence findings get sent back for re-extraction (up to 3 tries) |
| **ALIGN** | Maps entities to ontologies if you've configured them |
| **INDEX** | Generates SPECTER2 embeddings for semantic search |
| **HYPOTHESIZE** | Looks across findings to generate hypotheses, then tries to poke holes in them |

## Configuration

| File | What it controls |
|------|-----------------|
| `config/sources.yaml` | Where to find papers (RSS feeds, APIs) |
| `config/validators.yaml` | Physical bounds for numeric metrics in your domain |
| `config/rubrics.yaml` | How findings get graded |
| `config/confidence.yaml` | Weights and thresholds for confidence scoring |
| `config/ontologies.yaml` | Entity-to-ontology mappings |
| `config/models.yaml` | Which LLM to use and how |
| `config/routing.yaml` | How PDFs get routed to parsers |
| `config/skills.yaml` | Script subcommands and network policies |

## Database

SQLite with WAL mode, foreign keys, and sqlite-vec:

| Table | What's in it |
|-------|-------------|
| `papers` | Metadata, processing status, relevance scores |
| `findings` | Extracted claims with provenance quotes and confidence |
| `entities` | Materials, methods, organisms, metrics, etc. |
| `relations` | How entities connect (uses, measures, contradicts, etc.) |
| `hypotheses` | Generated hypotheses with critique logs |
| `confidence_scores` | Breakdown of each finding's confidence factors |
| `verification_results` | Which validators ran and what they found |
| `rubric_results` | Per-finding rubric grades with item-level detail |
| `extraction_provenance` | Which parser was used, how long it took, quality score |
| `feed_state` | Polling state for each feed |
| `graph_communities` | Clusters of related entities |
| `paper_embeddings` | SPECTER2 vectors for semantic search |

## Project Structure

```
├── config/                        # YAML configuration
│   ├── sources.yaml               # Feed definitions (start here)
│   ├── validators.yaml            # Numeric range validators
│   ├── rubrics.yaml               # Evaluation rubric
│   ├── confidence.yaml            # Scoring weights
│   ├── ontologies.yaml            # Domain ontologies
│   ├── models.yaml                # LLM settings
│   ├── routing.yaml               # Parser routing
│   └── skills.yaml                # Script manifest
├── schemas/                       # JSON Schema contracts
│   ├── scientific_conclusion_candidate.json
│   ├── rubric_result.json
│   └── rubric_item_result.json
├── scripts/                       # Pipeline and utilities
│   ├── orchestrator.sh            # Runs the 9-phase loop
│   ├── judge-score.sh             # Confidence scoring
│   ├── rubric-grade.sh            # Rubric evaluation
│   ├── feed-ingest.sh             # Feed polling
│   ├── pdf-fetch.sh               # PDF downloads
│   ├── parser-route.sh            # Parser routing
│   ├── structsense-extract.sh     # LLM extraction
│   ├── feedback-loop.sh           # Re-extraction loop
│   ├── ontology-align.sh          # Ontology mapping
│   ├── embed-index.sh             # Embedding generation
│   ├── hypothesis-gen.sh          # Hypothesis generation
│   ├── query-endpoint.py          # Flask API
│   ├── db-init.sh                 # Database setup
│   ├── db-backup.sh               # Backups
│   ├── health-check.sh            # Monitoring
│   └── lib/                       # Shared helpers
├── prompts/                       # LLM system prompts
├── examples/                      # Demo + fixtures
├── docs/                          # Architecture docs
├── launchd/                       # macOS scheduling
├── tests/                         # Test suite
└── runtime/                       # Mutable data (gitignored)
```

## Design Principles

1. **No finding without proof.** Every claim needs a verbatim quote from the source.
2. **The LLM reads, logic validates.** Numeric checks, unit checks, and rubric grading don't touch the LLM.
3. **Everything is inspectable.** JSON schemas define outputs. Database columns are typed. Rubric results explain themselves.
4. **Config, not code.** New domains, validators, and rubrics go in YAML files.
5. **Phases stand alone.** Each pipeline step reads from and writes to the database. Run them individually, skip them, or swap them out.

## Non-Goals

- **Not a platform.** No plugins, no SDK. Extend it by editing config or scripts.
- **Not a replacement for peer review.** It checks extraction quality, not scientific truth.
- **Not cloud-dependent.** One machine, SQLite, local LLM.
- **Not built for scale.** Built for thoroughness on a single researcher's hardware.

## Safety

- **Kill switch**: `echo '{}' > runtime/state/STOPPED.json` stops everything
- **Thermal guard**: Pauses when CPU temperature spikes (macOS)
- **Quote enforcement**: Findings without source quotes get flagged
- **Range validation**: Numbers checked against physical limits, no LLM involved
- **Backups**: Daily compressed SQLite snapshots, 14-day rotation
- **Auto-retry**: Failed papers get 3 more chances across future cycles

## Tests

```bash
bash tests/test-schema-validation.sh   # Database schema (17 checks)
bash tests/test-validators.sh          # Numeric validators (39 cases)
bash tests/test-rubric-grading.sh      # Rubric grading (29 cases)
bash tests/test-parser-routing.sh      # PDF parser tools (needs poppler)
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

Phases run one at a time — heavy components never overlap. Ollama unloads after 2 minutes idle.

## License

MIT — see [LICENSE](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
