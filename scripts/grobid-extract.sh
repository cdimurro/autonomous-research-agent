#!/usr/bin/env bash
# grobid-extract.sh — Tier 0: GROBID bibliographic spine + text extraction
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

PAPER_ID="${1:?Usage: grobid-extract.sh <paper_id>}"
export PAPER_ID
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3
import requests
import json
import os
import sys
import time
from datetime import datetime
from lxml import etree
from pathlib import Path

PAPER_ID = os.environ.get("PAPER_ID", "")
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"
PARSED_DIR = f"{RUNTIME_ROOT}/parsed"
GROBID_URL = os.environ.get("GROBID_URL", "http://localhost:8070")
os.makedirs(PARSED_DIR, exist_ok=True)

db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
paper = db.execute("SELECT * FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()
if not paper:
    print(f"Paper {PAPER_ID} not found", file=sys.stderr)
    sys.exit(1)

pdf_path = os.path.join(RUNTIME_ROOT, paper["pdf_path"])
if not os.path.exists(pdf_path):
    print(f"PDF not found: {pdf_path}", file=sys.stderr)
    sys.exit(1)

print(f"[grobid] Processing {PAPER_ID}: {paper['title'][:60]}...")
start_time = time.time()

# Call GROBID fulltext processing
try:
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{GROBID_URL}/api/processFulltextDocument",
            files={"input": f},
            data={"consolidateHeader": "1", "consolidateCitations": "0"},
            timeout=120
        )
    resp.raise_for_status()
    tei_xml = resp.text
except Exception as e:
    print(f"[grobid] ERROR: {e}", file=sys.stderr)
    sys.exit(1)

duration_ms = int((time.time() - start_time) * 1000)

# Save raw TEI XML
output_path = os.path.join(PARSED_DIR, f"{PAPER_ID}_grobid.xml")
with open(output_path, "w") as f:
    f.write(tei_xml)

# Parse TEI XML for metadata
ns = {"tei": "http://www.tei-c.org/ns/1.0"}
try:
    root = etree.fromstring(tei_xml.encode())

    # Extract title
    title_el = root.find(".//tei:titleStmt/tei:title", ns)
    title = title_el.text.strip() if title_el is not None and title_el.text else paper["title"]

    # Extract abstract
    abstract_el = root.find(".//tei:profileDesc/tei:abstract", ns)
    abstract = ""
    if abstract_el is not None:
        abstract = " ".join(abstract_el.itertext()).strip()

    # Extract authors
    authors = []
    for author in root.findall(".//tei:fileDesc//tei:author", ns):
        forename = author.find(".//tei:forename", ns)
        surname = author.find(".//tei:surname", ns)
        name = ""
        if forename is not None and forename.text:
            name = forename.text
        if surname is not None and surname.text:
            name = f"{name} {surname.text}".strip()
        if name:
            authors.append(name)

    # Extract section headers
    sections = []
    for head in root.findall(".//tei:body//tei:head", ns):
        if head.text:
            sections.append(head.text.strip())

    # Extract references count
    ref_count = len(root.findall(".//tei:listBibl/tei:biblStruct", ns))

    # Count pages (approximate from body text)
    body = root.find(".//tei:body", ns)
    body_text = " ".join(body.itertext()).strip() if body is not None else ""
    text_length = len(body_text)
    pages_approx = max(text_length // 3000, 1)  # rough estimate

    # Quality assessment
    quality_score = 0.0
    if text_length > 500:
        quality_score += 0.4
    if len(sections) >= 3:
        quality_score += 0.3
    if ref_count >= 5:
        quality_score += 0.2
    if abstract:
        quality_score += 0.1

    result = {
        "paper_id": PAPER_ID,
        "parser": "grobid",
        "tier": 0,
        "title": title,
        "abstract": abstract[:500] if abstract else None,
        "authors": authors[:20],
        "sections": sections,
        "ref_count": ref_count,
        "text_length": text_length,
        "pages_approx": pages_approx,
        "quality_score": round(quality_score, 2),
        "duration_ms": duration_ms
    }

except etree.XMLSyntaxError as e:
    result = {
        "paper_id": PAPER_ID,
        "parser": "grobid",
        "tier": 0,
        "error": f"XML parse error: {e}",
        "quality_score": 0.0,
        "duration_ms": duration_ms
    }

# Store provenance
import time as t
import random, string
prov_id = hex(int(t.time() * 1000))[2:] + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
rel_output = os.path.relpath(output_path, RUNTIME_ROOT)

db.execute(
    """INSERT INTO extraction_provenance
       (provenance_id, paper_id, parser_used, tier, pages_total, pages_processed,
        text_length, quality_score, quality_signals, parse_duration_ms, raw_output_path)
       VALUES (?, ?, 'grobid', 0, ?, ?, ?, ?, ?, ?, ?)""",
    (prov_id, PAPER_ID, result.get("pages_approx"), result.get("pages_approx"),
     result.get("text_length", 0), result.get("quality_score", 0),
     json.dumps({"sections": len(result.get("sections", [])), "refs": result.get("ref_count", 0)}),
     duration_ms, rel_output)
)

# Update paper metadata if GROBID found better data
if result.get("abstract") and not paper["abstract"]:
    db.execute("UPDATE papers SET abstract=? WHERE paper_id=?", (result["abstract"], PAPER_ID))
if result.get("authors") and not paper["authors"]:
    db.execute("UPDATE papers SET authors=? WHERE paper_id=?",
              (json.dumps(result["authors"]), PAPER_ID))

db.commit()
db.close()

print(json.dumps(result, indent=2))
PYEOF
