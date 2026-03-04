#!/usr/bin/env bash
# orchestrator.sh — Main 9-phase agent loop (STRUCTSENSE pipeline)
# Usage: orchestrator.sh --cycle | --phase <name>
set -euo pipefail

SCRIPT_DIR="${SCIRES_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}"
source "$SCRIPT_DIR/.env"

MODE="${1:---cycle}"

# Check kill switch
KILL_FILE="${SCIRES_RUNTIME_ROOT}/state/STOPPED.json"
if [ -f "$KILL_FILE" ]; then
    echo "[orchestrator] Kill switch active. Exiting."
    exit 0
fi

log() {
    local msg="$1"
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    echo "[$ts] $msg"

    # Append to orchestrator log
    local log_file="${SCIRES_RUNTIME_ROOT}/logs/orchestrator.jsonl"
    "$SCIRES_VENV/bin/python3" -c "
import json
entry = {'timestamp': '$ts', 'message': '''$msg'''}
with open('$log_file', 'a') as f:
    f.write(json.dumps(entry) + '\n')
"
}

check_kill() {
    if [ -f "$KILL_FILE" ]; then
        log "Kill switch activated mid-cycle. Aborting."
        exit 0
    fi
}

PHASE_TIMEOUT="${SCIRES_PHASE_TIMEOUT:-2700}"  # 45 min default per phase

# Portable timeout: prefer coreutils timeout/gtimeout, fallback to bash bg+wait
run_with_timeout() {
    local secs="$1"; shift
    if command -v timeout &>/dev/null; then
        timeout "$secs" "$@"
    elif command -v gtimeout &>/dev/null; then
        gtimeout "$secs" "$@"
    else
        "$@" &
        local pid=$!
        ( sleep "$secs"; kill "$pid" 2>/dev/null ) &
        local watcher=$!
        if wait "$pid" 2>/dev/null; then
            kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
            return 0
        else
            local rc=$?
            kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
            [ "$rc" -eq 143 ] && return 124  # killed by watcher = timeout
            return $rc
        fi
    fi
}

run_phase() {
    local phase_name="$1"
    local script="$2"
    shift 2
    local args=("$@")

    check_kill
    log "=== PHASE: $phase_name ==="
    local start_ts
    start_ts=$(date +%s)

    if run_with_timeout "$PHASE_TIMEOUT" bash "$SCRIPT_DIR/scripts/$script" "${args[@]}" 2>&1; then
        local end_ts
        end_ts=$(date +%s)
        local duration=$((end_ts - start_ts))
        log "Phase $phase_name completed in ${duration}s"
    else
        local exit_code=$?
        if [ "$exit_code" -eq 124 ]; then
            log "Phase $phase_name TIMED OUT after ${PHASE_TIMEOUT}s"
        else
            log "Phase $phase_name FAILED (exit $exit_code)"
        fi
    fi
}

if [ "$MODE" = "--cycle" ]; then
    log "=========================================="
    log "Starting orchestrator cycle"
    log "=========================================="

    # Pre-flight: Thermal guard
    THERMAL=$(/usr/sbin/sysctl -n kern.thermalpressure 2>/dev/null || echo 0)
    log "Pre-flight: thermal_pressure=$THERMAL"
    if [ "$THERMAL" -ge 2 ]; then
        log "Thermal pressure HIGH ($THERMAL). Waiting 10m before proceeding."
        sleep 600
        THERMAL=$(/usr/sbin/sysctl -n kern.thermalpressure 2>/dev/null || echo 0)
        if [ "$THERMAL" -ge 2 ]; then
            log "Thermal still high ($THERMAL). Aborting cycle."
            exit 0
        fi
    fi

    # Pre-flight: Check services
    if ! curl -s --max-time 5 "http://${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; then
        log "WARNING: Ollama not responding at ${OLLAMA_HOST}"
    fi
    if ! curl -s --max-time 5 "http://localhost:8070/api/isalive" 2>/dev/null | grep -q "true"; then
        log "WARNING: GROBID not responding"
    fi

    # Pre-flight: Auto-retry failed papers and reset stuck papers
    RESET_COUNT=$("$SCIRES_VENV/bin/python3" -c "
import sqlite3, os
db = sqlite3.connect(os.environ['SCIRES_RUNTIME_ROOT'] + '/db/scires.db')
# Reset failed papers (increment retry_count)
failed = db.execute(\"\"\"UPDATE papers SET status='queued', error_message=NULL, retry_count=retry_count+1
    WHERE status='failed' AND retry_count < 3\"\"\").rowcount
# Reset papers stuck in intermediate states for >1 hour
stuck = db.execute(\"\"\"UPDATE papers SET status='queued', error_message='reset: stuck', retry_count=retry_count+1
    WHERE status IN ('extracting','parsing','fetching')
    AND updated_at < datetime('now','-1 hour')
    AND retry_count < 3\"\"\").rowcount
db.commit()
print(f'{failed},{stuck}')
db.close()
")
    FAILED_RESET=$(echo "$RESET_COUNT" | cut -d, -f1)
    STUCK_RESET=$(echo "$RESET_COUNT" | cut -d, -f2)
    if [ "$FAILED_RESET" -gt 0 ] || [ "$STUCK_RESET" -gt 0 ]; then
        log "Pre-flight: Reset $FAILED_RESET failed + $STUCK_RESET stuck papers for retry"
    fi

    # Phase 1: INGEST — Poll feeds
    run_phase "INGEST" "feed-ingest.sh" "poll"

    # Phase 2: FETCH — Download PDFs
    run_phase "FETCH" "pdf-fetch.sh" "fetch-batch"

    # Phase 3: PARSE — Tiered parser routing
    run_phase "PARSE" "parser-route.sh" "route-batch"

    # Phase 4: EXTRACT — STRUCTSENSE LLM extraction
    run_phase "EXTRACT" "structsense-extract.sh" "extract-batch"

    # Phase 5: JUDGE — Confidence scoring + validation
    run_phase "JUDGE" "judge-score.sh" "score-batch"

    # Phase 5b: FEEDBACK — Critique loop on low-confidence papers
    LOW_CONF_PAPERS=$("$SCIRES_VENV/bin/python3" -c "
import sqlite3, os
db = sqlite3.connect(os.environ['SCIRES_RUNTIME_ROOT'] + '/db/scires.db')
rows = db.execute(\"\"\"
    SELECT DISTINCT f.paper_id FROM findings f
    JOIN papers p ON f.paper_id = p.paper_id
    WHERE p.status = 'judged'
    AND f.confidence < 0.65
    GROUP BY f.paper_id
    HAVING AVG(f.confidence) < 0.75
    LIMIT 5
\"\"\").fetchall()
print(' '.join(r[0] for r in rows))
db.close()
")
    if [ -n "$LOW_CONF_PAPERS" ]; then
        log "Phase FEEDBACK: Running critique on low-confidence papers: $LOW_CONF_PAPERS"
        for pid in $LOW_CONF_PAPERS; do
            check_kill
            log "  Feedback loop for $pid..."
            if bash "$SCRIPT_DIR/scripts/feedback-loop.sh" "$pid" 2 2>&1; then
                log "  Feedback for $pid complete"
            else
                log "  Feedback for $pid FAILED"
            fi
        done
    else
        log "Phase FEEDBACK: Skipped (all papers above confidence threshold)"
    fi

    # Phase 6: ALIGN — Ontology mapping
    run_phase "ALIGN" "ontology-align.sh" "align-batch"

    # Phase 7: INDEX — SPECTER2 embeddings
    run_phase "INDEX" "embed-index.sh" "index-batch"

    # Phase 8: HYPOTHESIZE — Generate hypotheses (daily-ish)
    # Only run if there are new indexed papers since last hypothesis run
    NEW_INDEXED=$("$SCIRES_VENV/bin/python3" -c "
import sqlite3, os
db = sqlite3.connect(os.environ['SCIRES_RUNTIME_ROOT'] + '/db/scires.db')
count = db.execute(\"SELECT COUNT(*) FROM papers WHERE status='indexed' AND updated_at >= datetime('now', '-4 hours')\").fetchone()[0]
print(count)
db.close()
")
    if [ "$NEW_INDEXED" -gt 0 ]; then
        run_phase "HYPOTHESIZE" "hypothesis-gen.sh" "generate"
    else
        log "Phase HYPOTHESIZE: Skipped (no new indexed papers)"
    fi

    log "=========================================="
    log "Orchestrator cycle complete"
    log "=========================================="

elif [ "$MODE" = "--phase" ]; then
    PHASE_NAME="${2:?Usage: orchestrator.sh --phase <name>}"
    case "$PHASE_NAME" in
        ingest)     run_phase "INGEST" "feed-ingest.sh" "poll" ;;
        fetch)      run_phase "FETCH" "pdf-fetch.sh" "fetch-batch" ;;
        parse)      run_phase "PARSE" "parser-route.sh" "route-batch" ;;
        extract)    run_phase "EXTRACT" "structsense-extract.sh" "extract-batch" ;;
        judge)      run_phase "JUDGE" "judge-score.sh" "score-batch" ;;
        align)      run_phase "ALIGN" "ontology-align.sh" "align-batch" ;;
        index)      run_phase "INDEX" "embed-index.sh" "index-batch" ;;
        hypothesize) run_phase "HYPOTHESIZE" "hypothesis-gen.sh" "generate" ;;
        digest)     run_phase "DIGEST" "daily-digest.sh" "generate" ;;
        *)          echo "Unknown phase: $PHASE_NAME" >&2; exit 1 ;;
    esac
else
    echo "Usage: orchestrator.sh --cycle | --phase <name>" >&2
    exit 1
fi
