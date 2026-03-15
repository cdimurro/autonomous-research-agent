#!/usr/bin/env bash
# Setup script for the PyBaMM sidecar environment.
#
# Creates an isolated Python 3.11 venv (.venv-pybamm/) with PyBaMM
# installed. This venv is used by the battery sidecar subprocess
# and is never imported by the main engine (Python 3.14).
#
# Usage:
#   bash scripts/setup_pybamm_sidecar.sh
#
# After setup, verify with:
#   bash scripts/setup_pybamm_sidecar.sh --check

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv-pybamm"
RUNNER="$REPO_ROOT/battery_sidecar/pybamm_runner.py"

# Find a compatible Python (3.10, 3.11, or 3.12)
find_python() {
    for py in python3.12 python3.11 python3.10; do
        if command -v "$py" &>/dev/null; then
            version=$("$py" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -eq 3 ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
                echo "$py"
                return 0
            fi
        fi
    done
    return 1
}

# Check mode
if [ "${1:-}" = "--check" ]; then
    echo "=== PyBaMM Sidecar Health Check ==="

    # 1. Venv exists
    if [ ! -d "$VENV_DIR" ]; then
        echo "FAIL: Sidecar venv not found at $VENV_DIR"
        echo "  Run: bash scripts/setup_pybamm_sidecar.sh"
        exit 1
    fi
    echo "PASS: Venv exists at $VENV_DIR"

    # 2. Python binary
    if [ ! -f "$VENV_DIR/bin/python3" ]; then
        echo "FAIL: Python binary not found in venv"
        exit 1
    fi
    PY_VER=$("$VENV_DIR/bin/python3" --version 2>&1)
    echo "PASS: Python binary found ($PY_VER)"

    # 3. PyBaMM importable
    if ! "$VENV_DIR/bin/python3" -c "import pybamm; print(f'PyBaMM {pybamm.__version__}')" 2>/dev/null; then
        echo "FAIL: PyBaMM not importable"
        exit 1
    fi
    echo "PASS: PyBaMM importable"

    # 4. Parameter set loadable
    if ! "$VENV_DIR/bin/python3" -c "
import pybamm
ps = pybamm.ParameterValues('Chen2020')
print(f'Chen2020 parameter set loaded ({len(ps)} parameters)')
" 2>/dev/null; then
        echo "FAIL: Chen2020 parameter set not loadable"
        exit 1
    fi
    echo "PASS: Chen2020 parameter set loadable"

    # 5. Runner script exists
    if [ ! -f "$RUNNER" ]; then
        echo "FAIL: Runner script not found at $RUNNER"
        exit 1
    fi
    echo "PASS: Runner script exists"

    # 6. Runner returns valid JSON
    RESULT=$(echo '{"dfn_params":{"lower_voltage_cut_off":2.5,"upper_voltage_cut_off":4.2},"pybamm_parameter_set":"Chen2020","experiments":["baseline_1c"]}' | "$VENV_DIR/bin/python3" "$RUNNER" 2>/dev/null)
    if [ $? -ne 0 ]; then
        echo "FAIL: Runner exited with error"
        echo "  Output: $RESULT"
        exit 1
    fi
    # Check it's valid JSON with success=true
    if echo "$RESULT" | "$VENV_DIR/bin/python3" -c "import json,sys; d=json.load(sys.stdin); assert d.get('success'), f'success={d.get(\"success\")}: {d.get(\"error\",\"\")}'" 2>/dev/null; then
        echo "PASS: Runner returns valid JSON with success=true"
    else
        echo "FAIL: Runner did not return success=true"
        echo "  Output: $RESULT"
        exit 1
    fi

    echo ""
    echo "=== All checks passed. Sidecar is operational. ==="
    exit 0
fi

# Setup mode
echo "=== Setting up PyBaMM sidecar environment ==="

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
    echo "ERROR: No compatible Python (3.10–3.12) found."
    echo "  Install Python 3.11 or 3.12 first:"
    echo "    brew install python@3.11"
    exit 1
fi

PY_VER=$("$PYTHON" --version 2>&1)
echo "Using $PYTHON ($PY_VER)"

# Create venv
if [ -d "$VENV_DIR" ]; then
    echo "Venv already exists at $VENV_DIR — recreating..."
    rm -rf "$VENV_DIR"
fi

echo "Creating venv at $VENV_DIR..."
"$PYTHON" -m venv "$VENV_DIR"

echo "Installing PyBaMM..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$REPO_ROOT/battery_sidecar/requirements.txt"

echo ""
echo "Setup complete. Running health check..."
echo ""
bash "$0" --check
