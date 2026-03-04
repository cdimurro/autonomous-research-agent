#!/usr/bin/env bash
# docling-extract.sh — Tier 1: Docling PDF-to-structured-text conversion
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

PAPER_ID="${1:?Usage: docling-extract.sh <paper_id> [--ocr] [--tables]}"
export PAPER_ID
export DOCLING_OCR_FLAG="${2:-}"
export DOCLING_TABLES_FLAG="${3:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3
import json
import os
import sys
import time
from pathlib import Path

PAPER_ID = os.environ.get("PAPER_ID", "")
USE_OCR = os.environ.get("DOCLING_OCR_FLAG", "") == "--ocr"
USE_TABLES = os.environ.get("DOCLING_TABLES_FLAG", "") == "--tables"
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"
PARSED_DIR = f"{RUNTIME_ROOT}/parsed"
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

print(f"[docling] Processing {PAPER_ID} (OCR={'ON' if USE_OCR else 'OFF'}, tables={'ON' if USE_TABLES else 'OFF'})...")
start_time = time.time()

try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat

    # Configure pipeline
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = USE_OCR
    pipeline_options.do_table_structure = USE_TABLES

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    # Convert
    result = converter.convert(pdf_path)
    doc = result.document

    # Extract structured content
    full_text = doc.export_to_markdown()
    tables_found = 0
    figures_found = 0
    sections = []

    # Count structural elements
    for item in doc.iterate_items():
        item_obj = item[1] if isinstance(item, tuple) else item
        label = getattr(item_obj, 'label', None) or str(type(item_obj).__name__)
        if 'table' in str(label).lower():
            tables_found += 1
        elif 'figure' in str(label).lower() or 'picture' in str(label).lower():
            figures_found += 1
        elif 'heading' in str(label).lower() or 'section' in str(label).lower():
            text = getattr(item_obj, 'text', '')
            if text:
                sections.append(text)

    text_length = len(full_text)
    _num_pages = getattr(doc, 'num_pages', None)
    if callable(_num_pages):
        _num_pages = _num_pages()
    page_count = int(_num_pages) if _num_pages else max(text_length // 3000, 1)

    duration_ms = int((time.time() - start_time) * 1000)

    # Quality scoring
    quality_score = 0.0
    if text_length > 1000:
        quality_score += 0.5
    if len(sections) >= 3:
        quality_score += 0.3
    if tables_found > 0 or not USE_TABLES:
        quality_score += 0.1
    if figures_found >= 0:
        quality_score += 0.1
    quality_score = min(quality_score, 1.0)

    # Save output
    output_path = os.path.join(PARSED_DIR, f"{PAPER_ID}_docling.json")
    output_data = {
        "paper_id": PAPER_ID,
        "markdown": full_text,
        "sections": sections,
        "tables_found": tables_found,
        "figures_found": figures_found,
        "text_length": text_length,
        "page_count": page_count
    }
    with open(output_path, "w") as f:
        json.dump(output_data, f)

    # Also save markdown for easy reading
    md_path = os.path.join(PARSED_DIR, f"{PAPER_ID}_docling.md")
    with open(md_path, "w") as f:
        f.write(full_text)

    # Store provenance
    import random, string
    prov_id = hex(int(time.time() * 1000))[2:] + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    rel_output = os.path.relpath(output_path, RUNTIME_ROOT)
    tier = 2 if USE_OCR else 1

    db.execute(
        """INSERT INTO extraction_provenance
           (provenance_id, paper_id, parser_used, tier, pages_total, pages_processed,
            tables_found, figures_found, text_length, quality_score,
            quality_signals, parse_duration_ms, raw_output_path)
           VALUES (?, ?, 'docling', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (prov_id, PAPER_ID, tier, page_count, page_count,
         tables_found, figures_found, text_length, round(quality_score, 2),
         json.dumps({"ocr": USE_OCR, "tables": USE_TABLES, "sections": len(sections)}),
         duration_ms, rel_output)
    )
    db.commit()

    # Log throughput
    s_per_page = (duration_ms / 1000.0) / max(page_count, 1)
    with open(f"{RUNTIME_ROOT}/logs/throughput.jsonl", "a") as f:
        from datetime import datetime
        f.write(json.dumps({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "paper_id": PAPER_ID,
            "parser": "docling",
            "tier": tier,
            "duration_ms": duration_ms,
            "pages": page_count,
            "s_per_page": round(s_per_page, 3)
        }) + "\n")

    result_info = {
        "paper_id": PAPER_ID,
        "parser": "docling",
        "tier": tier,
        "text_length": text_length,
        "sections": len(sections),
        "tables": tables_found,
        "figures": figures_found,
        "quality_score": round(quality_score, 2),
        "duration_ms": duration_ms,
        "s_per_page": round(s_per_page, 3)
    }
    print(json.dumps(result_info, indent=2))

except Exception as e:
    duration_ms = int((time.time() - start_time) * 1000)
    print(f"[docling] ERROR: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

db.close()
PYEOF
