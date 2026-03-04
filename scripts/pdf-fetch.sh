#!/usr/bin/env bash
# pdf-fetch.sh — Download paper PDFs, hash dedup, store under runtime/pdfs/
# Usage: pdf-fetch.sh fetch <paper_id> | fetch-batch
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-fetch-batch}"
export PAPER_ID_ARG="${2:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3
import requests
import hashlib
import os
import sys
import json
import time
import re
from datetime import datetime
from pathlib import Path

COMMAND = os.environ.get("COMMAND", "fetch-batch")
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"
PDF_DIR = f"{RUNTIME_ROOT}/pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

ARXIV_DELAY = 3  # seconds between arXiv requests
MAX_BATCH = 20

# DOI prefixes that are dataset repositories, not papers with PDFs
DATASET_DOI_PREFIXES = [
    "10.5281/zenodo",     # Zenodo
    "10.17632/",          # Mendeley Data
    "10.17638/",          # Liverpool Data Catalogue
    "10.6084/",           # Figshare
    "10.5061/dryad",      # Dryad
    "10.7910/dvn",        # Harvard Dataverse
    "10.18126/",          # Materials Data Facility
    "10.24435/",          # PANGAEA
]

def is_dataset_doi(doi):
    """Check if a DOI belongs to a data repository (not a paper)"""
    if not doi:
        return False
    doi_lower = doi.lower()
    return any(doi_lower.startswith(prefix) for prefix in DATASET_DOI_PREFIXES)

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row
    return db

EMAIL = "user@localhost"  # Set your email for Unpaywall API
UA = "AutonomousResearchAgent/1.0 (mailto:user@localhost)"

def resolve_arxiv(paper):
    """Resolve arXiv PDF URL from ID or source URL"""
    arxiv_id = paper["arxiv_id"]
    url = paper["source_url"]
    aid = arxiv_id or ""
    if not aid and url:
        m = re.search(r'(\d{4}\.\d{4,5})(v\d+)?', url)
        if m:
            aid = m.group(0)
    if aid:
        return f"https://arxiv.org/pdf/{aid}.pdf"
    return None

def resolve_via_unpaywall(doi):
    """Use Unpaywall API to find OA PDF URL for a DOI"""
    if not doi:
        return None
    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{doi}?email={EMAIL}",
            headers={"User-Agent": UA}, timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Try best OA location first
        best = data.get("best_oa_location") or {}
        pdf_url = best.get("url_for_pdf") or best.get("url")
        if pdf_url:
            return pdf_url
        # Try all OA locations
        for loc in (data.get("oa_locations") or []):
            u = loc.get("url_for_pdf") or loc.get("url")
            if u:
                return u
    except Exception as e:
        print(f"    [unpaywall] Error for {doi}: {e}")
    return None

def resolve_via_semantic_scholar(doi):
    """Use Semantic Scholar API to find OA PDF URL"""
    if not doi:
        return None
    try:
        resp = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=openAccessPdf",
            headers={"User-Agent": UA}, timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        oa = data.get("openAccessPdf") or {}
        return oa.get("url")
    except Exception as e:
        print(f"    [s2] Error for {doi}: {e}")
    return None

def resolve_via_openalex(doi):
    """Use OpenAlex API to find OA PDF URL"""
    if not doi:
        return None
    try:
        resp = requests.get(
            f"https://api.openalex.org/works/doi:{doi}",
            headers={"User-Agent": UA, "mailto": EMAIL}, timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        best = data.get("best_oa_location") or data.get("primary_location") or {}
        pdf_url = best.get("pdf_url")
        if pdf_url:
            return pdf_url
        # Try all locations
        for loc in (data.get("locations") or []):
            u = loc.get("pdf_url")
            if u:
                return u
    except Exception as e:
        print(f"    [openalex] Error for {doi}: {e}")
    return None

def resolve_pdf_url(paper):
    """Multi-source PDF resolution chain: arXiv → direct .pdf → Unpaywall → S2 → OpenAlex"""
    url = paper["source_url"]
    source = paper["source"]
    doi = paper["doi"]

    # 1. arXiv direct (always works)
    if source == "arxiv" or paper["arxiv_id"]:
        arxiv_url = resolve_arxiv(paper)
        if arxiv_url:
            return arxiv_url

    # 2. Direct .pdf URL
    if url and url.lower().endswith(".pdf"):
        return url

    # 3. Unpaywall (best for paywalled DOIs → OA copies)
    if doi:
        print(f"    [resolve] Trying Unpaywall for {doi}...")
        unpaywall_url = resolve_via_unpaywall(doi)
        if unpaywall_url:
            print(f"    [resolve] Unpaywall found: {unpaywall_url[:80]}")
            return unpaywall_url

        # 4. Semantic Scholar
        print(f"    [resolve] Trying Semantic Scholar for {doi}...")
        s2_url = resolve_via_semantic_scholar(doi)
        if s2_url:
            print(f"    [resolve] S2 found: {s2_url[:80]}")
            return s2_url

        # 5. OpenAlex
        print(f"    [resolve] Trying OpenAlex for {doi}...")
        oa_url = resolve_via_openalex(doi)
        if oa_url:
            print(f"    [resolve] OpenAlex found: {oa_url[:80]}")
            return oa_url

    # 6. No PDF available
    return None

def download_pdf(url, paper_id):
    """Download PDF with rate limiting and return (path, sha256)"""
    pdf_path = os.path.join(PDF_DIR, f"{paper_id}.pdf")

    headers = {
        "User-Agent": UA,
        "Accept": "application/pdf"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=60, stream=True,
                          allow_redirects=True)
        resp.raise_for_status()

        # Check content type
        ct = resp.headers.get("content-type", "")
        if "pdf" not in ct and "octet-stream" not in ct:
            # May be an HTML page, not a PDF
            if resp.content[:5] != b"%PDF-":
                return None, None, f"Not a PDF (content-type: {ct})"

        with open(pdf_path, "wb") as f:
            sha256 = hashlib.sha256()
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                sha256.update(chunk)

        file_hash = sha256.hexdigest()
        file_size = os.path.getsize(pdf_path)

        if file_size < 1000:
            os.remove(pdf_path)
            return None, None, f"File too small ({file_size} bytes)"

        return pdf_path, file_hash, None

    except requests.RequestException as e:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return None, None, str(e)

def fetch_paper(db, paper):
    """Fetch a single paper's PDF"""
    paper_id = paper["paper_id"]

    # Skip dataset DOIs
    if is_dataset_doi(paper["doi"]):
        db.execute(
            "UPDATE papers SET status='skipped', error_message='Dataset repository DOI, not a paper', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
            (paper_id,)
        )
        db.commit()
        print(f"  [pdf-fetch] {paper_id}: Skipped (dataset DOI: {paper['doi']})")
        return False

    url = resolve_pdf_url(paper)

    if not url:
        db.execute(
            "UPDATE papers SET status='failed', error_message='No PDF URL available', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
            (paper_id,)
        )
        db.commit()
        print(f"  [pdf-fetch] {paper_id}: No PDF URL")
        return False

    print(f"  [pdf-fetch] {paper_id}: Downloading from {url[:80]}...")
    pdf_path, file_hash, error = download_pdf(url, paper_id)

    if error:
        db.execute(
            "UPDATE papers SET status='failed', error_message=?, retry_count=retry_count+1, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
            (error, paper_id)
        )
        db.commit()
        print(f"  [pdf-fetch] {paper_id}: FAILED - {error}")
        return False

    # Check hash dedup
    existing = db.execute("SELECT paper_id FROM papers WHERE pdf_hash=? AND paper_id!=?",
                         (file_hash, paper_id)).fetchone()
    if existing:
        os.remove(pdf_path)
        db.execute(
            "UPDATE papers SET status='skipped', error_message='Duplicate PDF (hash match)', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
            (paper_id,)
        )
        db.commit()
        print(f"  [pdf-fetch] {paper_id}: Skipped (duplicate of {existing['paper_id']})")
        return False

    # Update paper record
    rel_path = os.path.relpath(pdf_path, RUNTIME_ROOT)
    db.execute(
        "UPDATE papers SET status='fetched', pdf_path=?, pdf_hash=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
        (rel_path, file_hash, paper_id)
    )
    db.commit()
    print(f"  [pdf-fetch] {paper_id}: OK ({os.path.getsize(pdf_path)} bytes)")
    return True

# Main
db = get_db()

if COMMAND == "retry-failed":
    # Reset previously failed papers back to queued for retry
    reset = db.execute(
        "UPDATE papers SET status='queued', error_message=NULL WHERE status='failed' AND retry_count < 3"
    ).rowcount
    db.commit()
    print(f"[pdf-fetch] Reset {reset} failed papers to queued for retry")
    COMMAND = "fetch-batch"  # Fall through to fetch

if COMMAND == "fetch-batch":
    papers = db.execute(
        "SELECT * FROM papers WHERE status='queued' ORDER BY relevance_score DESC LIMIT ?",
        (MAX_BATCH,)
    ).fetchall()

    print(f"[pdf-fetch] Fetching {len(papers)} papers...")
    fetched = 0
    for paper in papers:
        if fetch_paper(db, paper):
            fetched += 1
        # Rate limit
        source = paper["source"]
        if source == "arxiv":
            time.sleep(ARXIV_DELAY)
        else:
            time.sleep(1)

    print(f"\n[pdf-fetch] Fetched {fetched}/{len(papers)} PDFs")

    # Audit log
    with open(f"{RUNTIME_ROOT}/logs/audit.jsonl", "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "event": "pdf_fetch",
            "details": {"fetched": fetched, "attempted": len(papers)}
        }) + "\n")

elif COMMAND == "fetch":
    paper_id = os.environ.get("PAPER_ID_ARG", "") or None
    if not paper_id:
        print("Usage: pdf-fetch.sh fetch <paper_id>", file=sys.stderr)
        sys.exit(1)
    paper = db.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
    if not paper:
        print(f"Paper {paper_id} not found", file=sys.stderr)
        sys.exit(1)
    fetch_paper(db, paper)

db.close()
PYEOF
