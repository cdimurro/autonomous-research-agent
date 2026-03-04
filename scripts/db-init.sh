#!/usr/bin/env bash
# db-init.sh — Initialize the SQLite database with full schema
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

DB_PATH="${SCIRES_RUNTIME_ROOT}/db/scires.db"
PYTHON="${SCIRES_VENV}/bin/python3"

echo "[db-init] Initializing database at $DB_PATH"

"$PYTHON" << 'PYEOF'
import sqlite3
import sqlite_vec
import os
import sys

db_path = os.environ.get("SCIRES_RUNTIME_ROOT", "") + "/db/scires.db"
os.makedirs(os.path.dirname(db_path), exist_ok=True)

db = sqlite3.connect(db_path)
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)

db.executescript("""
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- ============================================================
-- CORE: Papers
-- ============================================================
CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    arxiv_id        TEXT UNIQUE,
    doi             TEXT UNIQUE,
    title           TEXT NOT NULL,
    abstract        TEXT,
    authors         TEXT,
    source          TEXT NOT NULL
                    CHECK(source IN ('arxiv','nature','openalex','rew','manual')),
    source_url      TEXT,
    publication_date TEXT,
    journal         TEXT,
    subjects        TEXT,
    fetched_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK(status IN (
                        'queued','fetched','parsing','parsed',
                        'extracting','extracted','judged','aligned',
                        'indexed','failed','skipped'
                    )),
    pdf_path        TEXT,
    pdf_hash        TEXT,
    relevance_score REAL,
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source);
CREATE INDEX IF NOT EXISTS idx_papers_fetched ON papers(fetched_at);
CREATE INDEX IF NOT EXISTS idx_papers_pdf_hash ON papers(pdf_hash);
CREATE INDEX IF NOT EXISTS idx_papers_pub_date ON papers(publication_date);

-- ============================================================
-- CORE: Extraction Provenance
-- ============================================================
CREATE TABLE IF NOT EXISTS extraction_provenance (
    provenance_id   TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    parser_used     TEXT NOT NULL
                    CHECK(parser_used IN ('grobid','docling','adaparse_vlm','adaparse_ocr')),
    tier            INTEGER NOT NULL CHECK(tier IN (0,1,2)),
    pages_total     INTEGER,
    pages_processed INTEGER,
    tables_found    INTEGER DEFAULT 0,
    figures_found   INTEGER DEFAULT 0,
    text_length     INTEGER,
    quality_score   REAL CHECK(quality_score BETWEEN 0.0 AND 1.0),
    quality_signals TEXT,
    parse_duration_ms INTEGER,
    raw_output_path TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_prov_paper ON extraction_provenance(paper_id);
CREATE INDEX IF NOT EXISTS idx_prov_tier ON extraction_provenance(tier);

-- ============================================================
-- CORE: Findings
-- ============================================================
CREATE TABLE IF NOT EXISTS findings (
    finding_id      TEXT PRIMARY KEY,
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    finding_type    TEXT NOT NULL
                    CHECK(finding_type IN (
                        'result','method','material','metric',
                        'claim','limitation','future_work','comparison'
                    )),
    content         TEXT NOT NULL,
    structured_data TEXT,
    confidence      REAL NOT NULL CHECK(confidence BETWEEN 0.0 AND 1.0),
    provenance_page INTEGER,
    provenance_section TEXT,
    provenance_quote TEXT,
    extraction_cycle INTEGER NOT NULL DEFAULT 1,
    judge_verdict   TEXT
                    CHECK(judge_verdict IS NULL OR judge_verdict IN ('accepted','revised','rejected')),
    judge_rationale TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_findings_paper ON findings(paper_id);
CREATE INDEX IF NOT EXISTS idx_findings_type ON findings(finding_type);
CREATE INDEX IF NOT EXISTS idx_findings_confidence ON findings(confidence);
CREATE INDEX IF NOT EXISTS idx_findings_verdict ON findings(judge_verdict);

-- ============================================================
-- CORE: Entities
-- ============================================================
CREATE TABLE IF NOT EXISTS entities (
    entity_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    canonical_name  TEXT,
    entity_type     TEXT NOT NULL
                    CHECK(entity_type IN (
                        'material','method','metric','organism',
                        'ecosystem','chemical','device','institution',
                        'dataset','software'
                    )),
    paper_id        TEXT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    section         TEXT,
    ontology_id     TEXT,
    ontology_source TEXT,
    properties      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_paper ON entities(paper_id);
CREATE INDEX IF NOT EXISTS idx_entities_ontology ON entities(ontology_id);

-- ============================================================
-- CORE: Relations
-- ============================================================
CREATE TABLE IF NOT EXISTS relations (
    relation_id     TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    source_type     TEXT NOT NULL
                    CHECK(source_type IN ('entity','finding','paper')),
    target_id       TEXT NOT NULL,
    target_type     TEXT NOT NULL
                    CHECK(target_type IN ('entity','finding','paper')),
    relation_type   TEXT NOT NULL
                    CHECK(relation_type IN (
                        'uses','measures','improves_on','contradicts',
                        'supports','cites','part_of','produces',
                        'degrades','contains','equivalent_to'
                    )),
    confidence      REAL NOT NULL DEFAULT 0.5 CHECK(confidence BETWEEN 0.0 AND 1.0),
    evidence        TEXT,
    paper_id        TEXT REFERENCES papers(paper_id),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_id, source_type);
CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_id, target_type);
CREATE INDEX IF NOT EXISTS idx_rel_type ON relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_rel_paper ON relations(paper_id);

-- ============================================================
-- CORE: Hypotheses
-- ============================================================
CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id   TEXT PRIMARY KEY,
    hypothesis      TEXT NOT NULL,
    domain          TEXT,
    evidence_ids    TEXT NOT NULL,
    supporting_count INTEGER NOT NULL DEFAULT 0,
    contradicting_count INTEGER NOT NULL DEFAULT 0,
    confidence      REAL NOT NULL CHECK(confidence BETWEEN 0.0 AND 1.0),
    status          TEXT NOT NULL DEFAULT 'proposed'
                    CHECK(status IN (
                        'proposed','under_review','supported',
                        'weakened','refuted','archived'
                    )),
    critique_log    TEXT,
    generated_from  TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_hyp_confidence ON hypotheses(confidence);
CREATE INDEX IF NOT EXISTS idx_hyp_domain ON hypotheses(domain);

-- ============================================================
-- CORE: Confidence Scores
-- ============================================================
CREATE TABLE IF NOT EXISTS confidence_scores (
    score_id        TEXT PRIMARY KEY,
    target_id       TEXT NOT NULL,
    target_type     TEXT NOT NULL
                    CHECK(target_type IN ('finding','entity','hypothesis','relation')),
    overall_score   REAL NOT NULL CHECK(overall_score BETWEEN 0.0 AND 1.0),
    factors         TEXT NOT NULL,
    judge_model     TEXT,
    judge_run_id    TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_cscore_target ON confidence_scores(target_id, target_type);

-- ============================================================
-- CORE: Verification Results
-- ============================================================
CREATE TABLE IF NOT EXISTS verification_results (
    verification_id TEXT PRIMARY KEY,
    finding_id      TEXT NOT NULL REFERENCES findings(finding_id) ON DELETE CASCADE,
    validator_name  TEXT NOT NULL,
    passed          INTEGER NOT NULL CHECK(passed IN (0,1)),
    input_value     TEXT,
    expected_range  TEXT,
    actual_parsed   TEXT,
    error_message   TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_verif_finding ON verification_results(finding_id);
CREATE INDEX IF NOT EXISTS idx_verif_passed ON verification_results(passed);

-- ============================================================
-- OPERATIONAL: Feed State
-- ============================================================
CREATE TABLE IF NOT EXISTS feed_state (
    feed_id         TEXT PRIMARY KEY,
    feed_url        TEXT NOT NULL,
    last_polled_at  TEXT,
    last_item_id    TEXT,
    items_total     INTEGER NOT NULL DEFAULT 0,
    items_accepted  INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ============================================================
-- OPERATIONAL: Runs
-- ============================================================
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    task_type       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK(status IN ('running','completed','failed','cancelled')),
    papers_processed INTEGER DEFAULT 0,
    findings_produced INTEGER DEFAULT 0,
    tokens_used     INTEGER DEFAULT 0,
    cost_estimate   REAL DEFAULT 0.0,
    duration_ms     INTEGER,
    error_message   TEXT,
    started_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_type);
CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);

-- ============================================================
-- GRAPH-RAG: Communities
-- ============================================================
CREATE TABLE IF NOT EXISTS graph_communities (
    community_id    TEXT PRIMARY KEY,
    name            TEXT,
    entity_ids      TEXT NOT NULL,
    summary         TEXT,
    paper_count     INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
""")

# Create sqlite-vec virtual tables
db.execute("""
CREATE VIRTUAL TABLE IF NOT EXISTS paper_embeddings USING vec0(
    paper_id TEXT PRIMARY KEY,
    embedding FLOAT[768]
)""")

db.execute("""
CREATE VIRTUAL TABLE IF NOT EXISTS finding_embeddings USING vec0(
    finding_id TEXT PRIMARY KEY,
    embedding FLOAT[768]
)""")

db.execute("""
CREATE VIRTUAL TABLE IF NOT EXISTS entity_embeddings USING vec0(
    entity_id TEXT PRIMARY KEY,
    embedding FLOAT[768]
)""")

db.commit()

# Verify
tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print(f"[db-init] Created {len(tables)} tables:")
for t in tables:
    print(f"  - {t[0]}")

vec_ver = db.execute("SELECT vec_version()").fetchone()[0]
print(f"[db-init] sqlite-vec version: {vec_ver}")

db.close()
print("[db-init] Database initialized successfully")
PYEOF
