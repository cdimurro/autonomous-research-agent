#!/usr/bin/env bash
# install-plists.sh — Generate and optionally install launchd plists
# Substitutes /PATH/TO/REPO and /PATH/TO/VENV in the template plists with actual paths.
#
# Usage:
#   bash install-plists.sh --generate-only   # Generate plists in launchd/generated/
#   bash install-plists.sh --install          # Generate + copy to ~/Library/LaunchAgents + load
#   bash install-plists.sh --uninstall        # Unload + remove from ~/Library/LaunchAgents
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source .env for paths if available
if [ -f "$REPO_ROOT/.env" ]; then
    source "$REPO_ROOT/.env"
fi

VENV="${SCIRES_VENV:-$HOME/research-venv}"
OUTDIR="$SCRIPT_DIR/generated"
LAUNCH_DIR="$HOME/Library/LaunchAgents"

PLIST_LABELS=(
    com.scires.orchestrator
    com.scires.query-endpoint
    com.scires.daily-digest
    com.scires.db-backup
    com.scires.ollama
)

generate_plists() {
    mkdir -p "$OUTDIR"

    for label in "${PLIST_LABELS[@]}"; do
        local src="$SCRIPT_DIR/${label}.plist"
        local dst="$OUTDIR/${label}.plist"
        if [ -f "$src" ]; then
            sed -e "s|/PATH/TO/REPO|${REPO_ROOT}|g" \
                -e "s|/PATH/TO/VENV|${VENV}|g" \
                "$src" > "$dst"
            echo "  Generated: $dst"
        else
            echo "  Skipped (not found): $src"
        fi
    done

    echo "Generated plists in $OUTDIR/"
}

install_plists() {
    generate_plists
    mkdir -p "$LAUNCH_DIR"
    for label in "${PLIST_LABELS[@]}"; do
        local src="$OUTDIR/${label}.plist"
        local dst="$LAUNCH_DIR/${label}.plist"
        if [ -f "$src" ]; then
            # Unload existing if present
            launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
            cp "$src" "$dst"
            launchctl bootstrap "gui/$(id -u)" "$dst"
            echo "  Installed and loaded: $label"
        fi
    done
    echo "All plists installed to $LAUNCH_DIR"
}

uninstall_plists() {
    for label in "${PLIST_LABELS[@]}"; do
        local dst="$LAUNCH_DIR/${label}.plist"
        launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
        rm -f "$dst"
        echo "  Unloaded and removed: $label"
    done
    echo "All plists removed from $LAUNCH_DIR"
}

MODE="${1:---generate-only}"
case "$MODE" in
    --generate-only) generate_plists ;;
    --install)       install_plists ;;
    --uninstall)     uninstall_plists ;;
    *)               echo "Usage: install-plists.sh --generate-only | --install | --uninstall" >&2; exit 1 ;;
esac
