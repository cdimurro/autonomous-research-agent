#!/usr/bin/env bash
# feedback-loop.sh — 1-3 cycle recursive critique for extraction refinement
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export PAPER_ID="${1:?Usage: feedback-loop.sh <paper_id>}"
export MAX_CYCLES="${2:-3}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, json, os, sys, subprocess
from datetime import datetime

PAPER_ID = os.environ.get("PAPER_ID", "")
MAX_CYCLES = int(os.environ.get("MAX_CYCLES", "3"))
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

db = get_db()
paper = db.execute("SELECT * FROM papers WHERE paper_id=?", (PAPER_ID,)).fetchone()
if not paper:
    print(f"Paper {PAPER_ID} not found", file=sys.stderr)
    sys.exit(1)

print(f"[feedback] Starting feedback loop for {PAPER_ID} (max {MAX_CYCLES} cycles)")

for cycle in range(1, MAX_CYCLES + 1):
    if cycle == 1:
        # Cycle 1: Initial extraction + judge (already done by orchestrator)
        pass
    else:
        # Check if previous cycle had rejections or low confidence
        rejected = db.execute(
            "SELECT COUNT(*) as cnt FROM findings WHERE paper_id=? AND judge_verdict='rejected' AND extraction_cycle=?",
            (PAPER_ID, cycle - 1)
        ).fetchone()["cnt"]

        avg_conf = db.execute(
            "SELECT AVG(confidence) as avg FROM findings WHERE paper_id=? AND extraction_cycle=?",
            (PAPER_ID, cycle - 1)
        ).fetchone()["avg"] or 0

        if rejected == 0 and avg_conf >= 0.75:
            print(f"[feedback] Cycle {cycle}: No rejections and avg confidence {avg_conf:.2f} >= 0.75. Stopping.")
            break

        print(f"[feedback] Cycle {cycle}: {rejected} rejected, avg confidence {avg_conf:.2f}. Re-extracting...")

        # Build critique context from rejected/low-confidence findings
        rejected_findings = db.execute(
            """SELECT content, judge_rationale, confidence FROM findings
               WHERE paper_id=? AND extraction_cycle=? AND (judge_verdict='rejected' OR confidence < 0.5)
               LIMIT 5""",
            (PAPER_ID, cycle - 1)
        ).fetchall()
        feedback_summary = "; ".join(
            f"[{f['confidence']:.2f}] {f['content'][:80]}... ({f['judge_rationale']})"
            for f in rejected_findings
        ) if rejected_findings else ""

        # Re-run extraction with critique context
        env = {**os.environ}
        if feedback_summary:
            env["SCIRES_FEEDBACK_CONTEXT"] = (
                f"The following findings were rejected or scored low in cycle {cycle-1}: "
                f"{feedback_summary}. "
                "Please improve accuracy: use exact verbatim quotes and verify numeric values."
            )
        result = subprocess.run(
            ["bash", f"{REPO_ROOT}/scripts/structsense-extract.sh", "extract", PAPER_ID],
            capture_output=True, text=True, timeout=600, env=env
        )
        if result.returncode != 0:
            print(f"[feedback] Extraction failed in cycle {cycle}: {result.stderr[:200]}", file=sys.stderr)
            break

        # Re-judge
        result = subprocess.run(
            ["bash", f"{REPO_ROOT}/scripts/judge-score.sh", "score", PAPER_ID],
            capture_output=True, text=True, timeout=300, env=env
        )

    # Check current state
    total = db.execute("SELECT COUNT(*) as cnt FROM findings WHERE paper_id=?", (PAPER_ID,)).fetchone()["cnt"]
    accepted = db.execute("SELECT COUNT(*) as cnt FROM findings WHERE paper_id=? AND judge_verdict='accepted'", (PAPER_ID,)).fetchone()["cnt"]

    print(f"[feedback] After cycle {cycle}: {accepted}/{total} findings accepted")

    if accepted > 0 and accepted / max(total, 1) >= 0.7:
        print(f"[feedback] Acceptance rate >= 70%. Stopping.")
        break

print(f"[feedback] Feedback loop complete for {PAPER_ID}")
db.close()
PYEOF
