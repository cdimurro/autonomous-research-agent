#!/usr/bin/env bash
# health-check.sh — System health, thermal, and throughput monitoring
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

PYTHON="${SCIRES_VENV}/bin/python3"

echo "=== Scientific Research Agent Health Check ==="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""

# 1. Ollama
echo "--- Ollama ---"
if curl -s --max-time 5 "http://${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; then
    MODELS=$(curl -s "http://${OLLAMA_HOST}/api/tags" | "$PYTHON" -c "import sys,json; models=json.load(sys.stdin).get('models',[]); print(', '.join(m['name'] for m in models))")
    echo "Status: UP"
    echo "Models: $MODELS"
else
    echo "Status: DOWN"
fi

# 2. GROBID
echo ""
echo "--- GROBID ---"
if curl -s --max-time 5 "http://localhost:8070/api/isalive" | grep -q "true"; then
    echo "Status: UP"
else
    echo "Status: DOWN"
fi

# 3. Database
echo ""
echo "--- Database ---"
"$PYTHON" << 'PYEOF'
import sqlite3, sqlite_vec, os
db_path = os.environ["SCIRES_RUNTIME_ROOT"] + "/db/scires.db"
db = sqlite3.connect(db_path)
db.enable_load_extension(True)
sqlite_vec.load(db)
db.row_factory = sqlite3.Row

papers = db.execute("SELECT status, COUNT(*) as cnt FROM papers GROUP BY status").fetchall()
print(f"Papers by status:")
for p in papers:
    print(f"  {p['status']}: {p['cnt']}")

total_findings = db.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
accepted = db.execute("SELECT COUNT(*) FROM findings WHERE judge_verdict='accepted'").fetchone()[0]
print(f"Findings: {total_findings} total, {accepted} accepted")

entities = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
print(f"Entities: {entities}")

hypotheses = db.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0]
print(f"Hypotheses: {hypotheses}")

paper_emb = db.execute("SELECT COUNT(*) FROM paper_embeddings").fetchone()[0]
print(f"Paper embeddings: {paper_emb}")

db_size = os.path.getsize(db_path)
print(f"Database size: {db_size / 1024 / 1024:.1f} MB")
db.close()
PYEOF

# 4. Memory
echo ""
echo "--- Memory ---"
vm_stat | head -8
echo ""
sysctl vm.swapusage 2>/dev/null || echo "Swap: N/A"

# 5. Thermal
echo ""
echo "--- Thermal ---"
THERMAL=$(sysctl -n kern.thermalpressure 2>/dev/null || echo "N/A")
echo "Thermal pressure: $THERMAL (0=nominal, 1=moderate, 2=heavy, 3=critical)"

# 6. Disk
echo ""
echo "--- Disk ---"
df -h / | tail -1

# 7. Docker
echo ""
echo "--- Docker ---"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Docker not available"

echo ""
echo "=== Health Check Complete ==="
