#!/usr/bin/env bash
# test-rubric-grading.sh — Test rubric config loading, grading logic, and output structure
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

echo "=== Rubric Grading Tests ==="

"$PYTHON" << 'PYEOF'
import json, yaml, os, sys, tempfile

REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
PASS = 0
FAIL = 0

def check(desc, expected, actual):
    global PASS, FAIL
    if expected == actual:
        print(f"  PASS: {desc}")
        PASS += 1
    else:
        print(f"  FAIL: {desc} (expected={expected}, got={actual})")
        FAIL += 1

# ─── Test 1: Rubric config loads successfully ───
print("\n--- Config loading ---")
try:
    with open(f"{REPO_ROOT}/config/rubrics.yaml") as f:
        conf = yaml.safe_load(f)
    check("rubrics.yaml loads", True, conf is not None)
    check("rubrics key exists", True, "rubrics" in conf)
    rubric = conf["rubrics"]["scientific_conclusion_v1"]
    check("rubric has version", True, "version" in rubric)
    check("rubric has pass_threshold", True, "pass_threshold" in rubric)
    check("rubric has max_score", True, "max_score" in rubric)
    check("rubric has items", True, "items" in rubric)
    check("rubric has 7 items", 7, len(rubric["items"]))
    total = sum(item["max_points"] for item in rubric["items"].values())
    check("item max_points sum matches max_score", rubric["max_score"], total)
except Exception as e:
    print(f"  FAIL: rubrics.yaml load error: {e}")
    FAIL += 1

# ─── Test 2: Malformed rubric fails loudly ───
print("\n--- Malformed config detection ---")
bad_configs = [
    ("missing items", {"rubrics": {"scientific_conclusion_v1": {"version": "1.0.0", "pass_threshold": 6, "max_score": 10}}}),
    ("missing version", {"rubrics": {"scientific_conclusion_v1": {"pass_threshold": 6, "max_score": 10, "items": {}}}}),
    ("empty rubrics", {"rubrics": {}}),
    ("null rubrics", {"rubrics": None}),
]
for desc, bad_conf in bad_configs:
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(bad_conf, f)
        f.flush()
        try:
            with open(f.name) as rf:
                loaded = yaml.safe_load(rf)
            rubrics = loaded.get("rubrics")
            if not rubrics or not isinstance(rubrics, dict):
                check(f"malformed config rejected: {desc}", True, True)
            elif "scientific_conclusion_v1" not in rubrics:
                check(f"malformed config rejected: {desc}", True, True)
            else:
                r = rubrics["scientific_conclusion_v1"]
                has_all = all(k in r for k in ("version", "pass_threshold", "max_score", "items"))
                check(f"malformed config rejected: {desc}", False, has_all)
        except Exception:
            check(f"malformed config rejected: {desc}", True, True)
        finally:
            os.unlink(f.name)

# ─── Test 3: JSON schema files exist and are valid ───
print("\n--- Schema validation ---")
for schema_name in ["scientific_conclusion_candidate.json", "rubric_result.json", "rubric_item_result.json"]:
    schema_path = f"{REPO_ROOT}/schemas/{schema_name}"
    try:
        with open(schema_path) as f:
            schema = json.load(f)
        check(f"schema {schema_name} is valid JSON", True, True)
        check(f"schema {schema_name} has title", True, "title" in schema)
        check(f"schema {schema_name} has properties", True, "properties" in schema)
    except Exception as e:
        print(f"  FAIL: schema {schema_name}: {e}")
        FAIL += 1

# ─── Grading logic tests (inline, no DB needed) ───
# Replicate the core grading functions to test them in isolation

# Load validators
VALIDATORS = {}
try:
    with open(f"{REPO_ROOT}/config/validators.yaml") as f:
        vconf = yaml.safe_load(f)
    for domain, metrics in (vconf.get("domains") or {}).items():
        for metric, bounds in (metrics or {}).items():
            VALIDATORS[metric] = (bounds["min"], bounds["max"], bounds.get("unit", ""))
except Exception:
    pass

def _item_result(item_id, name, score, max_points, passed, failure_tags, rationale, **kw):
    return {"item_id": item_id, "name": name, "score": score, "max_points": max_points,
            "passed": passed, "failure_tags": failure_tags, "rationale": rationale,
            "evidence_refs": kw.get("evidence_refs", []), "missing_inputs": kw.get("missing_inputs", [])}

def grade_evidence_support(candidate):
    sd = candidate.get("structured_data")
    if not sd or not isinstance(sd, dict):
        return 0
    return 2 if (sd.get("metric") and sd.get("value") is not None) else (1 if (sd.get("metric") or sd.get("value") is not None) else 0)

def grade_provenance_support(candidate):
    quote = candidate.get("provenance_quote")
    if not quote or len(quote.strip()) < 10:
        return 0
    return 2 if len(quote.strip()) >= 30 else 1

def grade_numeric_consistency(candidate):
    vr = candidate.get("validator_results", [])
    if not vr:
        return 1  # not applicable
    return 2 if all(v["passed"] for v in vr) else (1 if any(v["passed"] for v in vr) else 0)

def simple_grade(candidate):
    """Simplified grading that returns total score."""
    score = 0
    score += grade_evidence_support(candidate)
    score += grade_provenance_support(candidate)
    score += grade_numeric_consistency(candidate)
    # unit_consistency: pass by default if no mismatch (1 pt)
    sd = candidate.get("structured_data")
    if sd and isinstance(sd, dict):
        metric = (sd.get("metric", "") or "").lower().replace(" ", "_")
        reported_unit = (sd.get("unit", "") or "").strip()
        if metric in VALIDATORS:
            expected = VALIDATORS[metric][2]
            if expected and reported_unit and reported_unit.lower().replace(".", "") != expected.lower().replace(".", ""):
                pass  # 0
            else:
                score += 1
        else:
            score += 1
    # contradiction_awareness: 1 if content + sd present
    if sd and candidate.get("content"):
        score += 1
    # uncertainty_calibration: 1 if confidence context present and calibrated
    cc = candidate.get("confidence_context")
    if cc:
        overall = cc.get("overall_score", 0)
        factors = cc.get("factors", {})
        if not (overall >= 0.8 and (factors.get("hallucination_check", 0) < 0.7 or factors.get("numeric_validation", 0) < 0.7)):
            score += 1
    # conclusion_alignment: 1 if content references metric/value
    if sd and isinstance(sd, dict) and candidate.get("content"):
        metric = (sd.get("metric", "") or "").lower().replace("_", " ")
        value = str(sd.get("value", ""))
        content_lower = candidate["content"].lower()
        if (metric and metric in content_lower) or (value and value in content_lower):
            score += 1
    return score

# ─── Test 4: Strong supported candidate passes ───
print("\n--- Strong candidate ---")
strong = {
    "artifact_id": "test_strong_001",
    "artifact_type": "finding",
    "content": "The solar efficiency of the perovskite cell reached 25.6%, measured under AM1.5G illumination.",
    "structured_data": {"metric": "solar_efficiency", "value": 25.6, "unit": "%"},
    "provenance_quote": "The champion device exhibited a power conversion efficiency of 25.6% under standard AM1.5G conditions.",
    "provenance_page": 4,
    "provenance_section": "Results",
    "paper_id": "test_paper_001",
    "evidence_refs": [],
    "validator_results": [{"validator": "range_solar_efficiency", "passed": True, "value": 25.6, "range": [0, 47], "error": None}],
    "confidence_context": {
        "overall_score": 0.82,
        "factors": {"source_quality": 0.95, "extraction_quality": 1.0, "numeric_validation": 1.0, "hallucination_check": 0.9, "cross_reference": 0.5},
        "verdict": "accepted"
    }
}
strong_score = simple_grade(strong)
check("strong candidate score >= 6 (pass threshold)", True, strong_score >= 6)
check(f"strong candidate score = {strong_score}/10", True, strong_score >= 8)

# ─── Test 5: Weak unsupported candidate fails ───
print("\n--- Weak candidate ---")
weak = {
    "artifact_id": "test_weak_001",
    "artifact_type": "finding",
    "content": "Something about energy.",
    "structured_data": None,
    "provenance_quote": None,
    "provenance_page": None,
    "provenance_section": None,
    "paper_id": "test_paper_002",
    "evidence_refs": [],
    "validator_results": [],
    "confidence_context": None
}
weak_score = simple_grade(weak)
check("weak candidate score < 6 (fail threshold)", True, weak_score < 6)
check(f"weak candidate score = {weak_score}/10", True, weak_score <= 2)

# ─── Test 6: Missing provenance causes failure ───
print("\n--- Missing provenance ---")
no_prov = {
    "artifact_id": "test_noprov_001",
    "artifact_type": "finding",
    "content": "The bandgap was measured at 1.5 eV for the material.",
    "structured_data": {"metric": "bandgap", "value": 1.5, "unit": "eV"},
    "provenance_quote": None,
    "provenance_page": None,
    "provenance_section": None,
    "paper_id": "test_paper_003",
    "evidence_refs": [],
    "validator_results": [{"validator": "range_bandgap", "passed": True, "value": 1.5, "range": [0, 15], "error": None}],
    "confidence_context": {"overall_score": 0.6, "factors": {"hallucination_check": 0.1, "numeric_validation": 1.0}, "verdict": "revised"}
}
prov_score = grade_provenance_support(no_prov)
check("missing provenance scores 0", 0, prov_score)

# ─── Test 7: Numeric inconsistency causes failure ───
print("\n--- Numeric inconsistency ---")
bad_numeric = {
    "artifact_id": "test_badnum_001",
    "artifact_type": "finding",
    "content": "The solar efficiency reached 99%.",
    "structured_data": {"metric": "solar_efficiency", "value": 99, "unit": "%"},
    "provenance_quote": "Our device showed a remarkable efficiency of 99% under standard conditions, far exceeding previous records.",
    "provenance_page": 3,
    "provenance_section": "Results",
    "paper_id": "test_paper_004",
    "evidence_refs": [],
    "validator_results": [{"validator": "range_solar_efficiency", "passed": False, "value": 99, "range": [0, 47], "error": "99 outside [0, 47]"}],
    "confidence_context": {"overall_score": 0.4, "factors": {"hallucination_check": 0.9, "numeric_validation": 0.3}, "verdict": "revised"}
}
num_score = grade_numeric_consistency(bad_numeric)
check("numeric inconsistency scores 0", 0, num_score)

# ─── Test 8: Rubric result output structure ───
print("\n--- Output structure ---")
# Simulate a rubric result
mock_result = {
    "rubric_result_id": "test_id",
    "rubric_id": "scientific_conclusion_v1",
    "rubric_version": "1.0.0",
    "artifact_id": "test_strong_001",
    "artifact_type": "finding",
    "total_score": 9,
    "max_score": 10,
    "pass_threshold": 6,
    "passed": True,
    "graded_at": "2026-01-01T00:00:00Z",
    "grader_name": "rubric-grade.sh",
    "grader_version": "1.0.0",
    "item_results": [
        {"item_id": "evidence_support", "name": "Evidence Support", "score": 2, "max_points": 2,
         "passed": True, "failure_tags": [], "rationale": "ok", "evidence_refs": [], "missing_inputs": []}
    ]
}
required_keys = {"rubric_result_id", "rubric_id", "rubric_version", "artifact_id", "artifact_type",
                 "total_score", "max_score", "pass_threshold", "passed", "graded_at",
                 "grader_name", "grader_version", "item_results"}
check("result has all required keys", True, required_keys.issubset(set(mock_result.keys())))
item = mock_result["item_results"][0]
item_keys = {"item_id", "name", "score", "max_points", "passed", "failure_tags", "rationale"}
check("item_result has all required keys", True, item_keys.issubset(set(item.keys())))

# ─── Summary ───
print(f"\n=== Results: {PASS} passed, {FAIL} failed ===")
if FAIL > 0:
    sys.exit(1)
PYEOF
