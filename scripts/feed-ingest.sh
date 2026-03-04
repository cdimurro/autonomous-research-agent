#!/usr/bin/env bash
# feed-ingest.sh — Poll arXiv, Nature, OpenAlex, REW RSS/API feeds for new papers
# Usage: feed-ingest.sh poll | poll-source --source=<name> | status
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"
source "$SCRIPT_DIR/scripts/lib/db.sh"
source "$SCRIPT_DIR/scripts/lib/retry.sh"

export COMMAND="${1:-poll}"
export SOURCE_FILTER="${2:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

case "$COMMAND" in
    poll|poll-source|status)
        ;;
    *)
        echo "Usage: feed-ingest.sh poll | poll-source --source=<name> | status" >&2
        exit 1
        ;;
esac

# Main feed ingestion logic implemented in Python for RSS/API parsing
"$PYTHON" << 'PYEOF'
import sqlite3
import sqlite_vec
import feedparser
import requests
import json
import hashlib
import os
import sys
import time
import re
from datetime import datetime, timedelta
from pathlib import Path

import yaml

COMMAND = os.environ.get("COMMAND", "poll")
REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"

# Load sources config
with open(f"{REPO_ROOT}/config/sources.yaml") as f:
    config = yaml.safe_load(f)

settings = config.get("settings", {})
MAX_PAPERS = settings.get("max_papers_per_poll", 50)
RELEVANCE_THRESHOLD = settings.get("relevance_threshold", 0.3)
ARXIV_RATE_LIMIT = settings.get("rate_limit_arxiv_seconds", 3)

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row
    return db

def generate_id():
    ts = hex(int(time.time() * 1000))[2:]
    import random, string
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{ts}{rand}"

def keyword_relevance(title, abstract, keywords):
    """Simple keyword matching relevance score (0-1)"""
    if not keywords:
        return 1.0  # No filter = accept all
    text = f"{title or ''} {abstract or ''}".lower()
    matches = sum(1 for kw in keywords if kw.lower() in text)
    return min(matches / max(len(keywords) * 0.3, 1), 1.0)

def extract_arxiv_id(entry):
    """Extract arXiv ID from entry link or id"""
    link = entry.get("link", "") or entry.get("id", "")
    m = re.search(r'(\d{4}\.\d{4,5})(v\d+)?', link)
    return m.group(0) if m else None

def poll_rss_feed(feed_id, feed_config, db):
    """Poll an RSS feed and insert new papers"""
    url = feed_config["url"]
    keywords = feed_config.get("relevance_keywords", [])

    print(f"[feed-ingest] Polling {feed_id}: {url}")

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            raise Exception(f"Feed parse error: {feed.bozo_exception}")
    except Exception as e:
        db.execute(
            "UPDATE feed_state SET error_count = error_count + 1, last_error = ? WHERE feed_id = ?",
            (str(e), feed_id)
        )
        db.commit()
        print(f"[feed-ingest] ERROR polling {feed_id}: {e}", file=sys.stderr)
        return 0

    accepted = 0
    total = 0

    for entry in feed.entries[:MAX_PAPERS]:
        total += 1
        title = entry.get("title", "").strip()
        abstract = entry.get("summary", "").strip()
        link = entry.get("link", "")
        published = entry.get("published", "")
        authors = ", ".join(a.get("name", "") for a in entry.get("authors", []))

        if not title:
            continue

        # Source-specific ID extraction
        source = "arxiv" if "arxiv" in url else "nature" if "nature" in url else "rew"
        arxiv_id = extract_arxiv_id(entry) if source == "arxiv" else None
        doi = None

        # Check for DOI in various fields
        for field in ["prism_doi", "dc_identifier"]:
            if hasattr(entry, field):
                doi = getattr(entry, field)
                break

        # Dedup check
        if arxiv_id:
            existing = db.execute("SELECT paper_id FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
            if existing:
                continue
        if doi:
            existing = db.execute("SELECT paper_id FROM papers WHERE doi = ?", (doi,)).fetchone()
            if existing:
                continue

        # Relevance filter
        score = keyword_relevance(title, abstract, keywords)
        if score < RELEVANCE_THRESHOLD:
            continue

        # Insert paper
        paper_id = generate_id()
        try:
            db.execute(
                """INSERT INTO papers (paper_id, arxiv_id, doi, title, abstract, authors, source,
                   source_url, publication_date, relevance_score, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued')""",
                (paper_id, arxiv_id, doi, title, abstract, authors, source,
                 link, published[:10] if published else None, score)
            )
            accepted += 1
        except sqlite3.IntegrityError:
            continue  # Dedup caught by UNIQUE constraint

    db.commit()

    # Update feed state
    db.execute(
        """INSERT INTO feed_state (feed_id, feed_url, last_polled_at, items_total, items_accepted)
           VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'), ?, ?)
           ON CONFLICT(feed_id) DO UPDATE SET
           last_polled_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'),
           items_total = items_total + excluded.items_total,
           items_accepted = items_accepted + excluded.items_accepted,
           error_count = 0""",
        (feed_id, url, total, accepted)
    )
    db.commit()

    print(f"[feed-ingest] {feed_id}: {accepted}/{total} papers accepted (relevance >= {RELEVANCE_THRESHOLD})")
    return accepted

def poll_openalex(feed_id, feed_config, db):
    """Poll OpenAlex API"""
    base_url = feed_config["url"]
    params = dict(feed_config.get("params", {}))

    # Replace date placeholder
    today = datetime.utcnow().strftime("%Y-%m-%d")
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    for k, v in params.items():
        if isinstance(v, str):
            params[k] = v.replace("{today-7d}", week_ago)

    params["mailto"] = "user@localhost"  # OpenAlex polite pool — set your email

    print(f"[feed-ingest] Polling {feed_id}: {base_url}")

    try:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        db.execute(
            "UPDATE feed_state SET error_count = error_count + 1, last_error = ? WHERE feed_id = ?",
            (str(e), feed_id)
        )
        db.commit()
        print(f"[feed-ingest] ERROR polling {feed_id}: {e}", file=sys.stderr)
        return 0

    accepted = 0
    total = 0
    results = data.get("results", [])

    for work in results[:MAX_PAPERS]:
        total += 1
        title = work.get("title", "")
        doi = work.get("doi", "").replace("https://doi.org/", "") if work.get("doi") else None

        if not title:
            continue

        # Dedup
        if doi:
            existing = db.execute("SELECT paper_id FROM papers WHERE doi = ?", (doi,)).fetchone()
            if existing:
                continue

        abstract_inv = work.get("abstract_inverted_index", {})
        # Reconstruct abstract from inverted index
        abstract = ""
        if abstract_inv:
            word_positions = []
            for word, positions in abstract_inv.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            abstract = " ".join(w for _, w in word_positions)

        authors = ", ".join(
            a.get("author", {}).get("display_name", "")
            for a in work.get("authorships", [])[:10]
        )

        # Get PDF URL if available
        source_url = None
        oa = work.get("open_access", {})
        if oa.get("oa_url"):
            source_url = oa["oa_url"]
        elif work.get("primary_location", {}).get("pdf_url"):
            source_url = work["primary_location"]["pdf_url"]

        pub_date = work.get("publication_date", "")

        paper_id = generate_id()
        try:
            db.execute(
                """INSERT INTO papers (paper_id, doi, title, abstract, authors, source,
                   source_url, publication_date, relevance_score, status)
                   VALUES (?, ?, ?, ?, ?, 'openalex', ?, ?, 0.8, 'queued')""",
                (paper_id, doi, title, abstract, authors, source_url, pub_date)
            )
            accepted += 1
        except sqlite3.IntegrityError:
            continue

    db.commit()

    db.execute(
        """INSERT INTO feed_state (feed_id, feed_url, last_polled_at, items_total, items_accepted)
           VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'), ?, ?)
           ON CONFLICT(feed_id) DO UPDATE SET
           last_polled_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'),
           items_total = items_total + excluded.items_total,
           items_accepted = items_accepted + excluded.items_accepted,
           error_count = 0""",
        (feed_id, base_url, total, accepted)
    )
    db.commit()

    print(f"[feed-ingest] {feed_id}: {accepted}/{total} papers accepted")
    return accepted

def show_status(db):
    """Show feed state and paper counts"""
    feeds = db.execute("SELECT * FROM feed_state ORDER BY feed_id").fetchall()
    paper_counts = db.execute(
        "SELECT status, COUNT(*) as cnt FROM papers GROUP BY status"
    ).fetchall()

    result = {
        "feeds": [dict(f) for f in feeds],
        "paper_counts": {r["status"]: r["cnt"] for r in paper_counts},
        "total_papers": db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    }
    print(json.dumps(result, indent=2))

# Main
db = get_db()

if COMMAND == "status":
    show_status(db)
elif COMMAND in ("poll", "poll-source"):
    source_filter = None
    source_env = os.environ.get("SOURCE_FILTER", "")
    if source_env.startswith("--source="):
        source_filter = source_env.split("=", 1)[1]
    elif source_env:
        source_filter = source_env

    total_accepted = 0
    for feed_id, feed_config in config.get("feeds", {}).items():
        if source_filter and feed_id != source_filter:
            continue

        feed_type = feed_config.get("type", "rss")
        if feed_type == "rss":
            total_accepted += poll_rss_feed(feed_id, feed_config, db)
            # Rate limit between feeds
            if "arxiv" in feed_id:
                time.sleep(ARXIV_RATE_LIMIT)
            else:
                time.sleep(1)
        elif feed_type == "api":
            total_accepted += poll_openalex(feed_id, feed_config, db)
            time.sleep(1)

    print(f"\n[feed-ingest] Total: {total_accepted} new papers queued")
    result = {"total_accepted": total_accepted}
    # Log to audit
    with open(f"{RUNTIME_ROOT}/logs/audit.jsonl", "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": "feed_ingest",
            "details": result
        }) + "\n")

db.close()
PYEOF
