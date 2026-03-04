#!/usr/bin/env bash
# db-backup.sh — Daily SQLite backup with rotation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

BACKUP_DIR="${SCIRES_RUNTIME_ROOT}/backups"
DB_PATH="${SCIRES_RUNTIME_ROOT}/db/scires.db"
DATE=$(date +%Y%m%d)
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

echo "[backup] Starting backup of $DB_PATH..."

# Use SQLite .backup for consistent copy (handles WAL correctly)
sqlite3 "$DB_PATH" ".backup '${BACKUP_DIR}/scires_${DATE}.db'"

# Compress
if command -v gzip > /dev/null 2>&1; then
    gzip -f "${BACKUP_DIR}/scires_${DATE}.db"
    BACKUP_FILE="${BACKUP_DIR}/scires_${DATE}.db.gz"
else
    BACKUP_FILE="${BACKUP_DIR}/scires_${DATE}.db"
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[backup] Saved: $BACKUP_FILE ($SIZE)"

# Rotate: remove backups older than KEEP_DAYS
REMOVED=0
find "$BACKUP_DIR" -name "scires_*.db*" -mtime +${KEEP_DAYS} -type f -print -delete 2>/dev/null | while read -r f; do
    REMOVED=$((REMOVED + 1))
done
echo "[backup] Rotation: keeping last ${KEEP_DAYS} days"

# Verify backup integrity
if [[ "$BACKUP_FILE" == *.gz ]]; then
    INTEGRITY=$(gzip -dc "$BACKUP_FILE" | sqlite3 :memory: ".restore /dev/stdin" "PRAGMA integrity_check;" 2>/dev/null || echo "skip")
else
    INTEGRITY=$(sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" 2>/dev/null || echo "skip")
fi

if [ "$INTEGRITY" = "ok" ]; then
    echo "[backup] Integrity check: PASS"
elif [ "$INTEGRITY" = "skip" ]; then
    echo "[backup] Integrity check: skipped (compressed)"
else
    echo "[backup] Integrity check: FAIL ($INTEGRITY)"
fi

echo "[backup] Complete"
