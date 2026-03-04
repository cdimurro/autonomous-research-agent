#!/usr/bin/env bash
# lib/db.sh — SQLite helpers and state machine enforcement
# Source this file: source "$(dirname "$0")/lib/db.sh"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$SCRIPT_DIR/.env"

DB_PATH="${SCIRES_RUNTIME_ROOT}/db/scires.db"
PYTHON="${SCIRES_VENV}/bin/python3"

# Generate a ULID-like ID (timestamp + random)
generate_id() {
    "$PYTHON" -c "
import time, random, string
ts = hex(int(time.time() * 1000))[2:]
rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
print(f'{ts}{rand}')
"
}

# Execute a SQL query and return results as JSON
db_query_json() {
    local sql="$1"
    shift
    "$PYTHON" -c "
import sqlite3, json, sys
db = sqlite3.connect('$DB_PATH')
db.row_factory = sqlite3.Row
try:
    cur = db.execute('''$sql''', $@)
    rows = [dict(r) for r in cur.fetchall()]
    print(json.dumps(rows))
except Exception as e:
    print(json.dumps({'error': str(e)}), file=sys.stderr)
    sys.exit(1)
finally:
    db.close()
" "${@:+}"
}

# Execute a SQL statement (INSERT/UPDATE/DELETE)
db_execute() {
    local sql="$1"
    shift
    "$PYTHON" << PYEOF
import sqlite3, sys
db = sqlite3.connect('$DB_PATH')
db.execute("PRAGMA journal_mode = WAL")
db.execute("PRAGMA foreign_keys = ON")
db.execute("PRAGMA busy_timeout = 5000")
try:
    db.execute('''$sql''', [$(printf "'%s'," "$@" | sed 's/,$//')])
    db.commit()
except Exception as e:
    print(f"DB error: {e}", file=sys.stderr)
    sys.exit(1)
finally:
    db.close()
PYEOF
}

# State machine: valid transitions for papers.status
# Returns 0 if transition is valid, 1 if not
validate_transition() {
    local current="$1"
    local target="$2"

    case "$current" in
        queued)     [[ "$target" =~ ^(fetched|skipped|failed)$ ]] ;;
        fetched)    [[ "$target" =~ ^(parsing|skipped|failed)$ ]] ;;
        parsing)    [[ "$target" =~ ^(parsed|failed)$ ]] ;;
        parsed)     [[ "$target" =~ ^(extracting|skipped|failed)$ ]] ;;
        extracting) [[ "$target" =~ ^(extracted|failed)$ ]] ;;
        extracted)  [[ "$target" =~ ^(judged|failed)$ ]] ;;
        judged)     [[ "$target" =~ ^(aligned|failed)$ ]] ;;
        aligned)    [[ "$target" =~ ^(indexed|failed)$ ]] ;;
        failed)     [[ "$target" =~ ^(queued)$ ]] ;;
        skipped|indexed) return 1 ;;  # terminal states
        *) return 1 ;;
    esac
}

# Transition paper status with validation
transition_paper() {
    local paper_id="$1"
    local new_status="$2"
    local error_msg="${3:-}"

    local current
    current=$("$PYTHON" -c "
import sqlite3
db = sqlite3.connect('$DB_PATH')
row = db.execute('SELECT status FROM papers WHERE paper_id = ?', ('$paper_id',)).fetchone()
print(row[0] if row else 'NOT_FOUND')
db.close()
")

    if [ "$current" = "NOT_FOUND" ]; then
        echo "[db] Paper $paper_id not found" >&2
        return 1
    fi

    if ! validate_transition "$current" "$new_status"; then
        echo "[db] Invalid transition: $current -> $new_status for paper $paper_id" >&2
        return 1
    fi

    "$PYTHON" << PYEOF
import sqlite3
db = sqlite3.connect('$DB_PATH')
db.execute("PRAGMA journal_mode = WAL")
db.execute("PRAGMA foreign_keys = ON")
db.execute("PRAGMA busy_timeout = 5000")
error_msg = '''$error_msg''' if '''$error_msg''' else None
db.execute(
    "UPDATE papers SET status = ?, error_message = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id = ?",
    ('$new_status', error_msg, '$paper_id')
)
db.commit()
db.close()
PYEOF
    echo "[db] $paper_id: $current -> $new_status"
}

# Check kill switch
check_kill_switch() {
    local kill_file="${SCIRES_RUNTIME_ROOT}/state/STOPPED.json"
    if [ -f "$kill_file" ]; then
        echo "[db] Kill switch active: $kill_file exists. Aborting." >&2
        exit 99
    fi
}

# Log an audit event
audit_log() {
    local event="$1"
    local details="$2"
    local log_file="${SCIRES_RUNTIME_ROOT}/logs/audit.jsonl"

    "$PYTHON" -c "
import json, datetime
entry = {
    'timestamp': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'event': '$event',
    'details': $details
}
with open('$log_file', 'a') as f:
    f.write(json.dumps(entry) + '\n')
"
}

# Log throughput data
log_throughput() {
    local paper_id="$1"
    local parser="$2"
    local tier="$3"
    local duration_ms="$4"
    local pages="$5"
    local log_file="${SCIRES_RUNTIME_ROOT}/logs/throughput.jsonl"

    "$PYTHON" -c "
import json, datetime
s_per_page = ($duration_ms / 1000.0) / max($pages, 1)
entry = {
    'timestamp': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'paper_id': '$paper_id',
    'parser': '$parser',
    'tier': $tier,
    'duration_ms': $duration_ms,
    'pages': $pages,
    's_per_page': round(s_per_page, 3)
}
with open('$log_file', 'a') as f:
    f.write(json.dumps(entry) + '\n')
"
}
