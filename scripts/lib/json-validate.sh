#!/usr/bin/env bash
# lib/json-validate.sh — JSON schema validation helpers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${SCIRES_VENV}/bin/python3"

# Validate JSON string is well-formed
# Usage: json_valid <json_string>
json_valid() {
    echo "$1" | "$PYTHON" -c "import sys,json; json.load(sys.stdin)" 2>/dev/null
}

# Extract a field from JSON
# Usage: json_get <json_string> <field_path>
json_get() {
    "$PYTHON" -c "
import json, sys
data = json.loads('''$1''')
keys = '$2'.split('.')
for k in keys:
    if isinstance(data, dict):
        data = data.get(k)
    elif isinstance(data, list) and k.isdigit():
        data = data[int(k)]
    else:
        data = None
        break
print(json.dumps(data) if data is not None else '')
"
}

# Validate extraction output has required fields
# Usage: validate_extraction_output <json_string>
validate_extraction_output() {
    "$PYTHON" << 'PYEOF'
import json, sys

try:
    data = json.loads(sys.stdin.read())
except json.JSONDecodeError as e:
    print(json.dumps({"valid": False, "error": f"Invalid JSON: {e}"}))
    sys.exit(1)

errors = []

# Must have findings array
if "findings" not in data or not isinstance(data["findings"], list):
    errors.append("Missing or invalid 'findings' array")
else:
    for i, f in enumerate(data["findings"]):
        if "content" not in f:
            errors.append(f"Finding {i}: missing 'content'")
        if "finding_type" not in f:
            errors.append(f"Finding {i}: missing 'finding_type'")
        if "provenance_quote" not in f or not f["provenance_quote"]:
            errors.append(f"Finding {i}: missing 'provenance_quote' (copy-first evidence required)")
        if "confidence" not in f:
            errors.append(f"Finding {i}: missing 'confidence'")

# Entities are optional but must be well-formed if present
if "entities" in data and isinstance(data["entities"], list):
    for i, e in enumerate(data["entities"]):
        if "name" not in e:
            errors.append(f"Entity {i}: missing 'name'")
        if "entity_type" not in e:
            errors.append(f"Entity {i}: missing 'entity_type'")

if errors:
    print(json.dumps({"valid": False, "errors": errors}))
    sys.exit(1)
else:
    print(json.dumps({"valid": True, "findings_count": len(data.get("findings", [])), "entities_count": len(data.get("entities", []))}))
PYEOF
}
