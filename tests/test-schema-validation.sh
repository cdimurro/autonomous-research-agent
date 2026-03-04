#!/usr/bin/env bash
# test-schema-validation.sh — Verify SQLite schema integrity
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

DB_PATH="${SCIRES_RUNTIME_ROOT}/db/scires.db"
PYTHON="${SCIRES_VENV}/bin/python3"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local result="$2"
    if [ "$result" = "ok" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc ($result)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Schema Validation Tests ==="

# Check WAL mode
WAL=$(sqlite3 "$DB_PATH" "PRAGMA journal_mode;")
check "WAL mode enabled" "$([ "$WAL" = "wal" ] && echo ok || echo "$WAL")"

# Check foreign keys (must be enabled per-connection; verify scripts set it)
FK=$(sqlite3 "$DB_PATH" "PRAGMA foreign_keys=ON; PRAGMA foreign_keys;")
check "Foreign keys can be enabled" "$(echo "$FK" | grep -q "1" && echo ok || echo "off")"

# Check all required tables exist
for table in papers findings entities relations hypotheses confidence_scores verification_results feed_state runs extraction_provenance graph_communities; do
    EXISTS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='$table';")
    check "Table '$table' exists" "$([ "$EXISTS" = "1" ] && echo ok || echo "missing")"
done

# Check sqlite-vec virtual tables (skip if extension not available)
"$PYTHON" -c "
import sqlite3, os, sys
db = sqlite3.connect('$DB_PATH')
try:
    import sqlite_vec
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
except (AttributeError, ImportError):
    print('  SKIP: sqlite-vec not available (loadable extensions unsupported)')
    db.close()
    sys.exit(0)
for table in ['paper_embeddings', 'finding_embeddings', 'entity_embeddings']:
    try:
        db.execute(f'SELECT COUNT(*) FROM {table}')
        print(f'  PASS: Virtual table {table} accessible')
    except Exception as e:
        print(f'  FAIL: Virtual table {table}: {e}')
db.close()
"

# Check papers status column has valid values
INVALID=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM papers WHERE status NOT IN ('queued','fetched','parsing','parsed','extracting','extracted','judged','aligned','indexed','failed','skipped');")
check "All paper statuses valid" "$([ "$INVALID" = "0" ] && echo ok || echo "$INVALID invalid")"

# Check findings have paper_id foreign keys that resolve
ORPHANS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM findings f LEFT JOIN papers p ON f.paper_id=p.paper_id WHERE p.paper_id IS NULL;")
check "No orphaned findings" "$([ "$ORPHANS" = "0" ] && echo ok || echo "$ORPHANS orphans")"

# Check entities have paper_id foreign keys that resolve
ORPHANS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM entities e LEFT JOIN papers p ON e.paper_id=p.paper_id WHERE p.paper_id IS NULL;")
check "No orphaned entities" "$([ "$ORPHANS" = "0" ] && echo ok || echo "$ORPHANS orphans")"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
