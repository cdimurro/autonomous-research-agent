#!/usr/bin/env bash
# demo-rubric-eval.sh — End-to-end rubric evaluation demo
#
# Grades two scientific conclusion candidates (one strong, one weak) using
# the rubric grader, without requiring Ollama, GROBID, or a running database.
#
# Usage:
#   bash examples/demo-rubric-eval.sh
#
# Output:
#   examples/expected-output/demo_strong_001.rubric.json
#   examples/expected-output/demo_weak_001.rubric.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Minimal env setup — only need Python and PyYAML
if [ -f "$SCRIPT_DIR/.env" ]; then
    source "$SCRIPT_DIR/.env"
fi
PYTHON="${SCIRES_VENV:-$(which python3)}/bin/python3"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(which python3)"
fi

echo "=== Rubric Evaluation Demo ==="
echo ""
echo "This demo grades two scientific conclusion candidates against the"
echo "scientific_conclusion_v1 rubric (7 criteria, 10 points, pass threshold 6)."
echo ""

"$PYTHON" << 'PYEOF'
import json, yaml, os, sys, time
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if "__file__" in dir() else os.environ.get("SCIRES_REPO_ROOT", os.getcwd())
# Handle heredoc execution where __file__ is not available
if not os.path.exists(os.path.join(REPO_ROOT, "config")):
    REPO_ROOT = os.environ.get("SCIRES_REPO_ROOT", os.getcwd())

FIXTURES_PATH = os.path.join(REPO_ROOT, "examples", "fixtures.json")
OUTPUT_DIR = os.path.join(REPO_ROOT, "examples", "expected-output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load rubric
with open(os.path.join(REPO_ROOT, "config", "rubrics.yaml")) as f:
    rubric_conf = yaml.safe_load(f)
rubric = rubric_conf["rubrics"]["scientific_conclusion_v1"]
items_conf = rubric["items"]
PASS_THRESHOLD = rubric["pass_threshold"]
MAX_SCORE = rubric["max_score"]

# Load validators
VALIDATORS = {}
with open(os.path.join(REPO_ROOT, "config", "validators.yaml")) as f:
    vconf = yaml.safe_load(f)
for domain, metrics in (vconf.get("domains") or {}).items():
    for metric, bounds in (metrics or {}).items():
        VALIDATORS[metric] = (bounds["min"], bounds["max"], bounds.get("unit", ""))

# Load fixtures
with open(FIXTURES_PATH) as f:
    fixtures = json.load(f)

def generate_id():
    ts = hex(int(time.time() * 1000))[2:]
    import random, string
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{ts}{rand}"

def _item_result(item_id, name, score, max_points, passed, failure_tags, rationale, **kw):
    return {
        "item_id": item_id, "name": name, "score": score, "max_points": max_points,
        "passed": passed, "failure_tags": failure_tags, "rationale": rationale,
        "evidence_refs": kw.get("evidence_refs", []), "missing_inputs": kw.get("missing_inputs", [])
    }

def grade_item(item_id, item_conf, candidate):
    max_points = item_conf["max_points"]
    requires = item_conf.get("requires", [])
    name = item_id.replace("_", " ").title()
    missing_inputs = [r for r in requires if candidate.get(r) is None or candidate.get(r) == [] or candidate.get(r) == {}]
    if missing_inputs and len(missing_inputs) == len(requires):
        return _item_result(item_id, name, 0, max_points, False,
                            ["missing_required_inputs"], f"Required inputs missing: {', '.join(missing_inputs)}", missing_inputs=missing_inputs)

    if item_id == "evidence_support":
        sd = candidate.get("structured_data")
        if not sd or not isinstance(sd, dict):
            return _item_result(item_id, name, 0, max_points, False, ["no_structured_data"], "No structured data present.", missing_inputs=missing_inputs)
        has_metric = bool(sd.get("metric"))
        has_value = sd.get("value") is not None
        if has_metric and has_value:
            return _item_result(item_id, name, max_points, max_points, True, [], "Structured data has metric and value.")
        return _item_result(item_id, name, 1 if (has_metric or has_value) else 0, max_points, has_metric or has_value,
                            ["partial_structured_data"] if (has_metric or has_value) else ["empty_structured_data"],
                            "Structured data partially present." if (has_metric or has_value) else "No metric or value.")

    elif item_id == "provenance_support":
        quote = candidate.get("provenance_quote")
        if not quote or len(quote.strip()) < 10:
            return _item_result(item_id, name, 0, max_points, False, ["missing_provenance"], "No provenance quote or too short (<10 chars).", missing_inputs=missing_inputs)
        if len(quote.strip()) >= 30:
            return _item_result(item_id, name, max_points, max_points, True, [], f"Provenance quote present ({len(quote)} chars).")
        return _item_result(item_id, name, 1, max_points, True, ["short_provenance"], f"Provenance quote short ({len(quote)} chars).")

    elif item_id == "numeric_consistency":
        vr = candidate.get("validator_results", [])
        if not vr:
            return _item_result(item_id, name, 1, max_points, True, [], "No numeric validators applicable.")
        all_passed = all(v["passed"] for v in vr)
        refs = [v.get("validator", "") for v in vr]
        if all_passed:
            return _item_result(item_id, name, max_points, max_points, True, [], f"All {len(vr)} validators passed.", evidence_refs=refs)
        any_passed = any(v["passed"] for v in vr)
        if any_passed:
            return _item_result(item_id, name, 1, max_points, True, ["partial_range_violation"], "Some validators failed.", evidence_refs=refs)
        return _item_result(item_id, name, 0, max_points, False, ["range_violation"], f"All {len(vr)} validators failed.", evidence_refs=refs)

    elif item_id == "unit_consistency":
        sd = candidate.get("structured_data")
        if not sd or not isinstance(sd, dict):
            return _item_result(item_id, name, 0, max_points, False, ["no_structured_data"], "No structured data.", missing_inputs=missing_inputs)
        metric = (sd.get("metric", "") or "").lower().replace(" ", "_")
        reported_unit = (sd.get("unit", "") or "").strip()
        if metric in VALIDATORS:
            expected = VALIDATORS[metric][2]
            if expected and reported_unit:
                if reported_unit.lower().replace(".", "") == expected.lower().replace(".", ""):
                    return _item_result(item_id, name, max_points, max_points, True, [], f"Unit '{reported_unit}' matches expected '{expected}'.")
                return _item_result(item_id, name, 0, max_points, False, ["unit_mismatch"], f"Unit '{reported_unit}' != expected '{expected}'.")
        return _item_result(item_id, name, max_points, max_points, True, [], "No expected unit defined (pass by default).")

    elif item_id == "contradiction_awareness":
        sd = candidate.get("structured_data")
        content = candidate.get("content", "")
        if not sd or not isinstance(sd, dict) or not content:
            return _item_result(item_id, name, 0, max_points, False, ["insufficient_data"], "Cannot check without content and structured data.", missing_inputs=missing_inputs)
        value = str(sd.get("value", ""))
        metric = sd.get("metric", "")
        content_lower = content.lower()
        has_ref = value and (value in content or (metric and metric.lower() in content_lower))
        if has_ref:
            return _item_result(item_id, name, max_points, max_points, True, [], "Content references the reported metric/value.")
        return _item_result(item_id, name, max_points, max_points, True, [], "No detectable contradiction.")

    elif item_id == "uncertainty_calibration":
        cc = candidate.get("confidence_context")
        if not cc:
            return _item_result(item_id, name, 0, max_points, False, ["no_confidence"], "No confidence context available.", missing_inputs=missing_inputs)
        overall = cc.get("overall_score", 0)
        factors = cc.get("factors", {})
        hall = factors.get("hallucination_check", 0)
        numeric = factors.get("numeric_validation", 0)
        if overall >= 0.8 and (hall < 0.7 or numeric < 0.7):
            return _item_result(item_id, name, 0, max_points, False, ["overconfident"], f"Confidence {overall:.2f} but hall={hall:.2f}, numeric={numeric:.2f}.")
        return _item_result(item_id, name, max_points, max_points, True, [], f"Confidence {overall:.2f} calibrated with evidence quality.")

    elif item_id == "conclusion_alignment":
        sd = candidate.get("structured_data")
        content = candidate.get("content", "")
        if not sd or not isinstance(sd, dict) or not content:
            return _item_result(item_id, name, 0, max_points, False, ["insufficient_data"], "Cannot check without content and structured data.", missing_inputs=missing_inputs)
        metric = (sd.get("metric", "") or "").lower().replace("_", " ")
        value = str(sd.get("value", ""))
        content_lower = content.lower()
        if (metric and metric in content_lower) or (value and value in content):
            return _item_result(item_id, name, max_points, max_points, True, [], "Content aligns with structured metric/value.")
        return _item_result(item_id, name, 0, max_points, False, ["misaligned"], "Content does not reference metric or value.")

    return _item_result(item_id, name, 0, max_points, False, ["unknown_item"], f"No grading logic for '{item_id}'.")

def grade_candidate(candidate):
    result_id = generate_id()
    item_results = [grade_item(iid, iconf, candidate) for iid, iconf in items_conf.items()]
    total_score = sum(ir["score"] for ir in item_results)
    return {
        "rubric_result_id": result_id,
        "rubric_id": "scientific_conclusion_v1",
        "rubric_version": rubric["version"],
        "artifact_id": candidate["artifact_id"],
        "artifact_type": candidate["artifact_type"],
        "total_score": total_score,
        "max_score": MAX_SCORE,
        "pass_threshold": PASS_THRESHOLD,
        "passed": total_score >= PASS_THRESHOLD,
        "graded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grader_name": "demo-rubric-eval.sh",
        "grader_version": "1.0.0",
        "item_results": item_results
    }

# Grade each candidate
for candidate in fixtures["candidates"]:
    aid = candidate["artifact_id"]
    result = grade_candidate(candidate)

    # Write output
    out_path = os.path.join(OUTPUT_DIR, f"{aid}.rubric.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    # Display summary
    status = "PASS" if result["passed"] else "FAIL"
    print(f"--- {aid} ---")
    print(f"  Result: {status}  ({result['total_score']}/{result['max_score']}, threshold {result['pass_threshold']})")
    print()
    for ir in result["item_results"]:
        mark = "+" if ir["passed"] else "x"
        print(f"  [{mark}] {ir['name']}: {ir['score']}/{ir['max_points']}")
        print(f"      {ir['rationale']}")
        if ir["failure_tags"]:
            print(f"      tags: {ir['failure_tags']}")
    print()
    print(f"  Output: {out_path}")
    print()

print("=== Demo complete ===")
PYEOF
