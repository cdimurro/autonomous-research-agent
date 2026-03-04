#!/usr/bin/env bash
# daily-digest.sh — Generate daily research digest
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

COMMAND="${1:-generate}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, json, os, sys
from datetime import datetime, timedelta

RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"

db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row

cutoff = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

# Papers processed today
papers = db.execute("""
    SELECT status, COUNT(*) as cnt FROM papers
    WHERE updated_at >= ? GROUP BY status
""", (cutoff,)).fetchall()

# Top findings
top_findings = db.execute("""
    SELECT f.content, f.confidence, f.finding_type, p.title
    FROM findings f
    JOIN papers p ON f.paper_id = p.paper_id
    WHERE f.created_at >= ? AND f.judge_verdict = 'accepted'
    ORDER BY f.confidence DESC LIMIT 10
""", (cutoff,)).fetchall()

# Hypothesis updates
hyp_updates = db.execute("""
    SELECT hypothesis, confidence, status FROM hypotheses
    WHERE updated_at >= ? ORDER BY confidence DESC LIMIT 5
""", (cutoff,)).fetchall()

# System stats
total_papers = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
total_findings = db.execute("SELECT COUNT(*) FROM findings WHERE judge_verdict='accepted'").fetchone()[0]
total_entities = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
total_hypotheses = db.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0]

digest = f"""# Daily Research Digest — {datetime.utcnow().strftime("%Y-%m-%d")}

## Papers Processed (last 24h)
"""
for p in papers:
    digest += f"- {p['status']}: {p['cnt']}\n"

digest += f"\n## Top Findings (by confidence)\n"
for i, f in enumerate(top_findings, 1):
    digest += f"{i}. [{f['finding_type']}, conf={f['confidence']:.2f}] {f['content'][:150]}\n   Source: {f['title'][:60]}\n\n"

if hyp_updates:
    digest += f"\n## Hypothesis Updates\n"
    for h in hyp_updates:
        digest += f"- [{h['status']}, conf={h['confidence']:.2f}] {h['hypothesis'][:150]}\n"

digest += f"""
## System Statistics
- Total papers: {total_papers}
- Total accepted findings: {total_findings}
- Total entities: {total_entities}
- Total hypotheses: {total_hypotheses}
"""

# Save digest
digest_path = f"{RUNTIME_ROOT}/logs/digest_{datetime.utcnow().strftime('%Y%m%d')}.md"
with open(digest_path, "w") as f:
    f.write(digest)

print(digest)
print(f"\n[digest] Saved to {digest_path}")

db.close()
PYEOF
