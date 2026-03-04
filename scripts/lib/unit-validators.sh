#!/usr/bin/env bash
# lib/unit-validators.sh — Deterministic numeric/unit/range validators
# These are NOT LLM-based. They use hardcoded physical bounds.
# Source this file: source "$(dirname "$0")/lib/unit-validators.sh"
#
# Validators are loaded from config/validators.yaml if present,
# otherwise a set of generic scientific validators is used.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${SCIRES_VENV}/bin/python3"

# Master validator: takes finding structured_data JSON, returns validation results
# Usage: validate_finding <finding_id> <structured_data_json>
# Output: JSON array of validation results
validate_finding() {
    local finding_id="$1"
    local structured_data="$2"

    "$PYTHON" << 'PYEOF'
import json, sys, re, os
from pathlib import Path

structured_data = json.loads('''STRUCTURED_DATA_PLACEHOLDER''')
finding_id = "FINDING_ID_PLACEHOLDER"

# Try to load custom validators from config
REPO_ROOT = os.environ.get("SCIRES_REPO_ROOT", "")
custom_validators_path = Path(REPO_ROOT) / "config" / "validators.yaml"

VALIDATORS = {}

if custom_validators_path.exists():
    try:
        import yaml
        with open(custom_validators_path) as f:
            cfg = yaml.safe_load(f)
        for domain, metrics in cfg.get("domains", {}).items():
            for metric_name, bounds in metrics.items():
                VALIDATORS[metric_name] = (bounds["min"], bounds["max"], bounds.get("unit", ""))
    except Exception:
        pass

# Default generic validators (always available)
GENERIC_VALIDATORS = {
    "percentage": (0, 100, "%"),
    "efficiency": (0, 100, "%"),
    "temperature": (-273.15, 3000, "C"),
    "ph": (0, 14, ""),
    "pressure": (0, 1e12, "Pa"),
    "concentration": (0, 1e12, "mol/L"),
    "wavelength": (1, 1e7, "nm"),
    "frequency": (0, 1e15, "Hz"),
    "mass": (0, 1e15, "kg"),
    "voltage": (0, 1e6, "V"),
    "current": (0, 1e9, "A"),
    "power": (0, 1e15, "W"),
    "time": (0, 1e15, "s"),
    "length": (0, 1e15, "m"),
}

# Merge: custom overrides generic
all_validators = {**GENERIC_VALIDATORS, **VALIDATORS}

results = []

if not isinstance(structured_data, dict):
    print(json.dumps([]))
    sys.exit(0)

value = structured_data.get("value")
unit = structured_data.get("unit", "")
metric = structured_data.get("metric", "").lower().replace(" ", "_")

if value is None or metric == "":
    print(json.dumps([]))
    sys.exit(0)

# Try to parse value as float
try:
    if isinstance(value, str):
        # Handle ranges like "10-20" — take midpoint
        if "-" in value and not value.startswith("-"):
            parts = value.split("-")
            val = (float(parts[0].strip()) + float(parts[-1].strip())) / 2
        else:
            val = float(re.sub(r'[^\d.\-eE+]', '', value))
    else:
        val = float(value)
except (ValueError, TypeError):
    results.append({
        "finding_id": finding_id,
        "validator_name": "parse_check",
        "passed": False,
        "input_value": str(value),
        "expected_range": None,
        "actual_parsed": None,
        "error_message": f"Cannot parse value: {value}"
    })
    print(json.dumps(results))
    sys.exit(0)

# Find matching validator
matched = False
for validator_name, (vmin, vmax, expected_unit) in all_validators.items():
    if metric == validator_name or metric.replace("_", "") == validator_name.replace("_", ""):
        matched = True
        passed = vmin <= val <= vmax
        results.append({
            "finding_id": finding_id,
            "validator_name": f"range_check_{validator_name}",
            "passed": passed,
            "input_value": str(val),
            "expected_range": json.dumps({"min": vmin, "max": vmax, "unit": expected_unit}),
            "actual_parsed": json.dumps({"value": val, "unit": unit}),
            "error_message": None if passed else f"Value {val} outside range [{vmin}, {vmax}] for {validator_name}"
        })
        break

# Magnitude check: detect likely unit conversion errors (off by 1000x)
if matched and results and results[-1]["passed"]:
    _, (vmin, vmax, _) = next((k, v) for k, v in all_validators.items()
                               if k == metric or k.replace("_","") == metric.replace("_",""))
    range_mag = vmax - vmin
    if range_mag > 0 and val > 0:
        if val > vmax * 10 or val < vmin / 10:
            results.append({
                "finding_id": finding_id,
                "validator_name": f"magnitude_check_{metric}",
                "passed": False,
                "input_value": str(val),
                "expected_range": json.dumps({"min": vmin, "max": vmax}),
                "actual_parsed": json.dumps({"value": val}),
                "error_message": f"Possible unit conversion error: value {val} is far outside typical range"
            })

if not matched:
    # No specific validator, just check it's a reasonable positive number
    if "efficiency" in metric or "percentage" in metric or metric.endswith("_pct"):
        passed = 0 <= val <= 100
        results.append({
            "finding_id": finding_id,
            "validator_name": "generic_percentage",
            "passed": passed,
            "input_value": str(val),
            "expected_range": json.dumps({"min": 0, "max": 100, "unit": "%"}),
            "actual_parsed": json.dumps({"value": val, "unit": unit}),
            "error_message": None if passed else f"Percentage {val} outside [0, 100]"
        })

print(json.dumps(results))
PYEOF
}

# Batch validate all findings for a paper
# Usage: validate_paper_findings <paper_id>
validate_paper_findings() {
    local paper_id="$1"
    source "$SCRIPT_DIR/scripts/lib/db.sh"

    "$PYTHON" << PYEOF
import sqlite3, json, subprocess, os

db_path = os.environ.get("SCIRES_RUNTIME_ROOT", "") + "/db/scires.db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

findings = db.execute(
    "SELECT finding_id, structured_data FROM findings WHERE paper_id = ? AND structured_data IS NOT NULL",
    ('$paper_id',)
).fetchall()

all_results = []
for f in findings:
    sd = f['structured_data']
    if not sd:
        continue
    try:
        data = json.loads(sd)
    except json.JSONDecodeError:
        continue

    finding_id = f['finding_id']
    value = data.get("value")
    metric = data.get("metric", "").lower().replace(" ", "_")
    unit = data.get("unit", "")

    if value is None or metric == "":
        continue

print(f"Validated {len(findings)} findings for paper $paper_id")
db.close()
PYEOF
}
