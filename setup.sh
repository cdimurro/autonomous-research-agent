#!/usr/bin/env bash
# setup.sh — One-command setup for Autonomous Research Agent
# Usage: bash setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Autonomous Research Agent Setup ==="
echo "Repo: $REPO_ROOT"
echo ""

# ── Step 1: Create .env if missing ──
if [ ! -f "$REPO_ROOT/.env" ]; then
    echo "[1/6] Creating .env from .env.example..."
    sed "s|/path/to/this/repo|$REPO_ROOT|g; s|/path/to/your/python-venv|$HOME/research-venv|g" \
        "$REPO_ROOT/.env.example" > "$REPO_ROOT/.env"
    echo "  Created .env — review and adjust paths if needed."
else
    echo "[1/6] .env already exists, skipping."
fi

source "$REPO_ROOT/.env"
VENV="${SCIRES_VENV:-$HOME/research-venv}"

# ── Step 2: Create Python venv ──
if [ ! -d "$VENV" ]; then
    echo "[2/6] Creating Python venv at $VENV..."
    python3 -m venv "$VENV"
    echo "  Created venv."
else
    echo "[2/6] Venv already exists at $VENV, skipping."
fi

# ── Step 3: Install Python dependencies ──
echo "[3/6] Installing Python dependencies..."
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$REPO_ROOT/requirements.txt" -q
echo "  Dependencies installed."

# ── Step 4: Create runtime directories ──
echo "[4/6] Creating runtime directories..."
RUNTIME="${SCIRES_RUNTIME_ROOT:-$REPO_ROOT/runtime}"
mkdir -p "$RUNTIME"/{db,pdfs,parsed,extractions,backups,logs,state,workspace,cache}
echo "  Runtime directories ready at $RUNTIME"

# ── Step 5: Initialize database ──
if [ ! -f "$RUNTIME/db/scires.db" ]; then
    echo "[5/6] Initializing database..."
    bash "$REPO_ROOT/scripts/db-init.sh"
    echo "  Database initialized."
else
    echo "[5/6] Database already exists, skipping."
fi

# ── Step 6: Generate launchd plists ──
echo "[6/6] Generating launchd plists..."
bash "$REPO_ROOT/launchd/install-plists.sh" --generate-only
echo ""

# ── Summary ──
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Review .env and adjust settings if needed"
echo "  2. Install Ollama: brew install ollama"
echo "     Pull model: ollama pull qwen3.5:9b-q4_K_M"
echo "  3. Start GROBID: docker run -d --name grobid -p 8070:8070 --memory=2048m lfoppiano/grobid:0.8.2"
echo "  4. Run a test cycle: bash scripts/orchestrator.sh --cycle"
echo "  5. For 24/7 operation: bash launchd/install-plists.sh --install"
echo "  6. Run tests: bash tests/test-validators.sh"
echo ""
echo "Docs: See README.md for full architecture and API reference."
