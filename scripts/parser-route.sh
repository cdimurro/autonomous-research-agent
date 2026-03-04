#!/usr/bin/env bash
# parser-route.sh — AdaParse-lite tiered parser routing
# Usage: parser-route.sh route <paper_id> | route-batch | classify <paper_id>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-route-batch}"
export PAPER_ID="${2:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3
import subprocess
import json
import os
import sys
import time
from pathlib import Path

COMMAND = os.environ.get("COMMAND", "route-batch")
PAPER_ID = os.environ.get("PAPER_ID", "") or None
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row
    return db

def classify_pdf(pdf_path):
    """Extract PDF features for routing decision"""
    features = {
        "has_text_layer": False,
        "chars_per_page": 0,
        "font_quality": 0.0,
        "image_density": 0.0,
        "page_count": 0
    }

    # Get page count
    try:
        result = subprocess.run(
            ["pdfinfo", pdf_path],
            capture_output=True, text=True, timeout=30
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Pages:"):
                features["page_count"] = int(line.split(":")[1].strip())
                break
    except Exception:
        features["page_count"] = 1

    pages = max(features["page_count"], 1)

    # Check text layer
    try:
        result = subprocess.run(
            ["pdftotext", pdf_path, "-"],
            capture_output=True, text=True, timeout=60
        )
        text_chars = len(result.stdout)
        features["chars_per_page"] = text_chars / pages
        features["has_text_layer"] = features["chars_per_page"] > 100
    except Exception:
        pass

    # Check font quality
    try:
        result = subprocess.run(
            ["pdffonts", pdf_path],
            capture_output=True, text=True, timeout=30
        )
        lines = result.stdout.strip().split("\n")[2:]  # Skip header
        total_fonts = len(lines)
        embedded = sum(1 for l in lines if "yes" in l.lower().split())
        features["font_quality"] = embedded / max(total_fonts, 1)
    except Exception:
        features["font_quality"] = 0.0

    # Check image density
    try:
        result = subprocess.run(
            ["pdfimages", "-list", pdf_path],
            capture_output=True, text=True, timeout=30
        )
        image_lines = result.stdout.strip().split("\n")[2:]  # Skip header
        features["image_density"] = len(image_lines) / pages
    except Exception:
        features["image_density"] = 0.0

    return features

def route_paper(db, paper):
    """Determine and execute the best parser for a paper"""
    parse_start = time.time()
    paper_id = paper["paper_id"]
    pdf_path = os.path.join(RUNTIME_ROOT, paper["pdf_path"])

    if not os.path.exists(pdf_path):
        print(f"[parser-route] {paper_id}: PDF not found at {pdf_path}", file=sys.stderr)
        return False

    # Update status
    db.execute("UPDATE papers SET status='parsing', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?", (paper_id,))
    db.commit()

    # Step 1: Classify PDF features
    features = classify_pdf(pdf_path)
    print(f"[parser-route] {paper_id}: features={json.dumps(features)}")

    # Step 2: Always run Tier 0 (GROBID)
    print(f"[parser-route] {paper_id}: Running Tier 0 (GROBID)...")
    try:
        grobid_result = subprocess.run(
            ["bash", f"{REPO_ROOT}/scripts/grobid-extract.sh", paper_id],
            capture_output=True, text=True, timeout=180,
            env={**os.environ}
        )
        if grobid_result.returncode != 0:
            print(f"[parser-route] GROBID error: {grobid_result.stderr[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[parser-route] GROBID exception: {e}", file=sys.stderr)

    # Step 3: Route to Tier 1 or Tier 2
    ocr_flag = ""
    tables_flag = ""
    tier = 1

    if features["has_text_layer"] and features["font_quality"] >= 0.7:
        # Tier 1: Docling, OCR OFF, tables OFF
        tier = 1
        print(f"[parser-route] {paper_id}: Routing to Tier 1 (Docling, no OCR)")
    elif features["has_text_layer"] and features["font_quality"] < 0.7:
        # Tier 1+OCR: Docling with OCR
        tier = 1
        ocr_flag = "--ocr"
        print(f"[parser-route] {paper_id}: Routing to Tier 1+OCR (Docling, OCR ON)")
    else:
        # Tier 2: Full OCR
        tier = 2
        ocr_flag = "--ocr"
        tables_flag = "--tables"
        print(f"[parser-route] {paper_id}: Routing to Tier 2 (Docling, full OCR)")

    # Run Docling
    cmd = ["bash", f"{REPO_ROOT}/scripts/docling-extract.sh", paper_id]
    if ocr_flag:
        cmd.append(ocr_flag)
    if tables_flag:
        cmd.append(tables_flag)

    try:
        docling_result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            env={**os.environ}
        )
        if docling_result.returncode != 0:
            print(f"[parser-route] Docling error: {docling_result.stderr[:200]}", file=sys.stderr)

            # Quality gate: if Tier 1 failed, try Tier 2
            if tier == 1 and not ocr_flag:
                print(f"[parser-route] {paper_id}: Escalating to Tier 2 (OCR)")
                cmd2 = ["bash", f"{REPO_ROOT}/scripts/docling-extract.sh", paper_id, "--ocr", "--tables"]
                docling_result = subprocess.run(
                    cmd2, capture_output=True, text=True, timeout=300,
                    env={**os.environ}
                )
                if docling_result.returncode != 0:
                    db.execute(
                        "UPDATE papers SET status='failed', error_message=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
                        (f"Both Tier 1 and Tier 2 failed", paper_id)
                    )
                    db.commit()
                    return False

        # Check quality gate
        if docling_result.stdout:
            try:
                docling_info = json.loads(docling_result.stdout)
                quality = docling_info.get("quality_score", 0)
                if quality < 0.3 and tier < 2:
                    print(f"[parser-route] {paper_id}: Quality {quality} < 0.3, escalating...")
                    cmd_escalate = ["bash", f"{REPO_ROOT}/scripts/docling-extract.sh", paper_id, "--ocr", "--tables"]
                    subprocess.run(cmd_escalate, capture_output=True, text=True, timeout=300, env={**os.environ})
            except json.JSONDecodeError:
                pass

    except subprocess.TimeoutExpired:
        db.execute(
            "UPDATE papers SET status='failed', error_message='Parser timeout', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
            (paper_id,)
        )
        db.commit()
        return False

    # Update status to parsed
    db.execute("UPDATE papers SET status='parsed', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?", (paper_id,))
    db.commit()

    # Throughput logging
    parse_end = time.time()
    duration_ms = int((parse_end - parse_start) * 1000)
    pages = max(features.get("page_count", 1), 1)
    s_per_page = round(duration_ms / 1000 / pages, 2)
    throughput_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "paper_id": paper_id,
        "tier": tier,
        "ocr": bool(ocr_flag),
        "pages": pages,
        "duration_ms": duration_ms,
        "s_per_page": s_per_page
    }
    throughput_log = f"{RUNTIME_ROOT}/logs/throughput.jsonl"
    with open(throughput_log, "a") as f:
        f.write(json.dumps(throughput_entry) + "\n")

    print(f"[parser-route] {paper_id}: Parsed successfully (tier={tier}, {s_per_page} s/page)")
    return True

# Main
db = get_db()

if COMMAND == "classify" and PAPER_ID:
    paper = db.execute("SELECT * FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()
    if paper and paper["pdf_path"]:
        features = classify_pdf(os.path.join(RUNTIME_ROOT, paper["pdf_path"]))
        print(json.dumps(features, indent=2))
    else:
        print("Paper not found or no PDF", file=sys.stderr)
        sys.exit(1)

elif COMMAND == "route" and PAPER_ID:
    paper = db.execute("SELECT * FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()
    if paper:
        route_paper(db, paper)
    else:
        print(f"Paper {PAPER_ID} not found", file=sys.stderr)
        sys.exit(1)

elif COMMAND == "route-batch":
    papers = db.execute(
        "SELECT * FROM papers WHERE status='fetched' LIMIT 10"
    ).fetchall()
    print(f"[parser-route] Processing {len(papers)} papers...")
    parsed = 0
    for paper in papers:
        if route_paper(db, paper):
            parsed += 1
    print(f"\n[parser-route] Parsed {parsed}/{len(papers)} papers")

db.close()
PYEOF
