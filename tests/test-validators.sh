#!/usr/bin/env bash
# test-validators.sh — Test deterministic numeric validators from judge-score.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

PYTHON="${SCIRES_VENV}/bin/python3"
PASS=0
FAIL=0

check() {
    local desc="$1"
    local expected="$2"
    local actual="$3"
    if [ "$expected" = "$actual" ]; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc (expected=$expected, got=$actual)"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Deterministic Validator Tests ==="

"$PYTHON" << 'PYEOF'
import json, re

# Copy validators from judge-score.sh
VALIDATORS = {
    "energy_density_gravimetric": (1, 2000, "Wh/kg"),
    "energy_density_volumetric": (1, 5000, "Wh/L"),
    "power_density": (1, 50000, "W/kg"),
    "solar_efficiency": (0, 47, "%"),
    "power_conversion_efficiency": (0, 47, "%"),
    "voltage": (0, 5, "V"),
    "capacity": (1, 500, "mAh/g"),
    "cycle_life": (1, 100000, "cycles"),
    "coulombic_efficiency": (0, 100, "%"),
    "bandgap": (0, 15, "eV"),
    "temperature": (-273.15, 3000, "C"),
    "ph": (0, 14, ""),
    "biodiversity_index": (0, 1, ""),
    "biomass_density": (0, 2000, "t/ha"),
    "soil_organic_carbon": (0, 30, "%"),
    "efficiency": (0, 100, "%"),
    "percentage": (0, 100, "%"),
}

def validate(metric, value):
    if metric not in VALIDATORS:
        return None
    vmin, vmax, _ = VALIDATORS[metric]
    try:
        val = float(value)
    except (ValueError, TypeError):
        return False
    return vmin <= val <= vmax

# Test cases: (metric, value, expected_pass)
tests = [
    # Energy — valid
    ("energy_density_gravimetric", 250, True),
    ("energy_density_gravimetric", 1, True),
    ("energy_density_gravimetric", 2000, True),
    # Energy — invalid
    ("energy_density_gravimetric", 0, False),
    ("energy_density_gravimetric", 5000, False),
    ("energy_density_gravimetric", -100, False),
    # Solar efficiency — valid
    ("solar_efficiency", 25.6, True),
    ("solar_efficiency", 0, True),
    ("solar_efficiency", 47, True),
    # Solar efficiency — invalid
    ("solar_efficiency", 48, False),
    ("solar_efficiency", -1, False),
    ("solar_efficiency", 100, False),
    # Voltage — valid
    ("voltage", 3.7, True),
    ("voltage", 0, True),
    # Voltage — invalid
    ("voltage", 6, False),
    ("voltage", -0.5, False),
    # Temperature — valid
    ("temperature", 25, True),
    ("temperature", -273.15, True),
    ("temperature", 2500, True),
    # Temperature — invalid
    ("temperature", -300, False),
    ("temperature", 3500, False),
    # pH — valid
    ("ph", 7, True),
    ("ph", 0, True),
    ("ph", 14, True),
    # pH — invalid
    ("ph", -1, False),
    ("ph", 15, False),
    # Biodiversity — valid
    ("biodiversity_index", 0.5, True),
    ("biodiversity_index", 0, True),
    ("biodiversity_index", 1, True),
    # Biodiversity — invalid
    ("biodiversity_index", -0.1, False),
    ("biodiversity_index", 1.5, False),
    # Soil organic carbon — valid
    ("soil_organic_carbon", 5, True),
    # Soil organic carbon — invalid
    ("soil_organic_carbon", 35, False),
    # Bandgap — valid
    ("bandgap", 1.5, True),
    ("bandgap", 0, True),
    # Bandgap — invalid
    ("bandgap", 16, False),
    # Percentage — valid
    ("percentage", 50, True),
    # Percentage — invalid
    ("percentage", 101, False),
    ("percentage", -5, False),
]

passed = 0
failed = 0
for metric, value, expected in tests:
    result = validate(metric, value)
    if result == expected:
        print(f"  PASS: {metric}={value} -> {result}")
        passed += 1
    else:
        print(f"  FAIL: {metric}={value} -> {result} (expected {expected})")
        failed += 1

print(f"\n=== Results: {passed} passed, {failed} failed ===")
if failed > 0:
    exit(1)
PYEOF
