#!/usr/bin/env bash
# test-parser-routing.sh — Test AdaParse-lite PDF classification and tier routing
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

PYTHON="${SCIRES_VENV}/bin/python3"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local expected="$2"
    local actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc (expected=$expected, got=$actual)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Parser Routing Tests ==="

# Test 1: Verify poppler tools are available
echo ""
echo "--- Tool Availability ---"
for tool in pdftotext pdffonts pdfimages pdfinfo; do
    if command -v "$tool" > /dev/null 2>&1; then
        echo "  PASS: $tool found at $(which $tool)"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $tool not found in PATH"
        FAIL=$((FAIL + 1))
    fi
done

# Test 2: Classify an actual indexed PDF (if any exist)
echo ""
echo "--- PDF Classification ---"

"$PYTHON" << 'PYEOF'
import sqlite3, subprocess, json, os

RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row

# Find a fetched/indexed paper with a PDF
paper = db.execute("SELECT paper_id, pdf_path FROM papers WHERE pdf_path IS NOT NULL LIMIT 1").fetchone()
if not paper:
    print("  SKIP: No PDFs available for classification test")
    exit(0)

pdf_path = os.path.join(RUNTIME_ROOT, paper["pdf_path"])
if not os.path.exists(pdf_path):
    print(f"  SKIP: PDF not found at {pdf_path}")
    exit(0)

paper_id = paper["paper_id"]
print(f"  Testing classification on {paper_id}...")

# Run pdfinfo
result = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True, timeout=30)
pages = 0
for line in result.stdout.split("\n"):
    if line.startswith("Pages:"):
        pages = int(line.split(":")[1].strip())
        break

passed = 0
failed = 0

if pages > 0:
    print(f"  PASS: pdfinfo detected {pages} pages")
    passed += 1
else:
    print(f"  FAIL: pdfinfo could not detect pages")
    failed += 1

# Run pdftotext
result = subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True, timeout=60)
chars = len(result.stdout)
chars_per_page = chars / max(pages, 1)

if chars > 0:
    print(f"  PASS: pdftotext extracted {chars} chars ({chars_per_page:.0f} chars/page)")
    passed += 1
else:
    print(f"  FAIL: pdftotext extracted 0 chars")
    failed += 1

# Run pdffonts
result = subprocess.run(["pdffonts", pdf_path], capture_output=True, text=True, timeout=30)
font_lines = result.stdout.strip().split("\n")[2:]  # Skip header
total_fonts = len(font_lines)
embedded = sum(1 for l in font_lines if "yes" in l.lower().split())
font_quality = embedded / max(total_fonts, 1)

if total_fonts > 0:
    print(f"  PASS: pdffonts found {total_fonts} fonts, quality={font_quality:.2f}")
    passed += 1
else:
    print(f"  WARN: pdffonts found 0 fonts (may be image-based PDF)")
    passed += 1

# Routing decision
has_text = chars_per_page > 100
if has_text and font_quality >= 0.7:
    tier = "Tier 1 (no OCR)"
elif has_text:
    tier = "Tier 1+OCR"
else:
    tier = "Tier 2 (full OCR)"

print(f"  INFO: Would route to {tier}")
print(f"  Features: has_text={has_text}, font_quality={font_quality:.2f}, chars/page={chars_per_page:.0f}")

print(f"\n=== Classification: {passed} passed, {failed} failed ===")
db.close()
exit(failed)
PYEOF

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
