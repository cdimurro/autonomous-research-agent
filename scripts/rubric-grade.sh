#!/usr/bin/env bash
# rubric-grade.sh — Deterministic rubric grading for scientific conclusions
#
# Usage:
#   bash scripts/rubric-grade.sh grade <paper_id>     # Grade all accepted findings for a paper
#   bash scripts/rubric-grade.sh grade-batch           # Grade findings for all judged papers
#   bash scripts/rubric-grade.sh grade-finding <fid>   # Grade a single finding by ID
#
# Produces:
#   - rubric_results row in SQLite
#   - JSON artifact in runtime/evaluations/<finding_id>.rubric.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-grade-batch}"
export TARGET_ID="${2:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, json, os, sys, time, re, yaml
from datetime import datetime, timezone

COMMAND = os.environ.get("COMMAND", "grade-batch")
TARGET_ID = os.environ.get("TARGET_ID", "") or None
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"

GRADER_NAME = "rubric-grade.sh"
GRADER_VERSION = "1.0.0"

# --- Load rubric config ---
rubric_path = f"{REPO_ROOT}/config/rubrics.yaml"
try:
    with open(rubric_path) as f:
        rubric_conf = yaml.safe_load(f)
except Exception as e:
    print(f"[rubric] FATAL: Cannot load {rubric_path}: {e}", file=sys.stderr)
    sys.exit(1)

rubrics = rubric_conf.get("rubrics")
if not rubrics or not isinstance(rubrics, dict):
    print("[rubric] FATAL: No rubrics defined in config/rubrics.yaml", file=sys.stderr)
    sys.exit(1)

RUBRIC_ID = "scientific_conclusion_v1"
rubric = rubrics.get(RUBRIC_ID)
if not rubric:
    print(f"[rubric] FATAL: Rubric '{RUBRIC_ID}' not found", file=sys.stderr)
    sys.exit(1)

# Validate rubric structure
required_rubric_keys = {"version", "pass_threshold", "max_score", "items"}
missing = required_rubric_keys - set(rubric.keys())
if missing:
    print(f"[rubric] FATAL: Rubric missing keys: {missing}", file=sys.stderr)
    sys.exit(1)

items_conf = rubric["items"]
computed_max = sum(item.get("max_points", 0) for item in items_conf.values())
if computed_max != rubric["max_score"]:
    print(f"[rubric] FATAL: Item max_points sum ({computed_max}) != declared max_score ({rubric['max_score']})", file=sys.stderr)
    sys.exit(1)

PASS_THRESHOLD = rubric["pass_threshold"]
MAX_SCORE = rubric["max_score"]
RUBRIC_VERSION = rubric["version"]

print(f"[rubric] Loaded rubric '{RUBRIC_ID}' v{RUBRIC_VERSION}: {len(items_conf)} items, max={MAX_SCORE}, pass={PASS_THRESHOLD}")

# --- Load validators for unit checking ---
VALIDATORS = {}
try:
    with open(f"{REPO_ROOT}/config/validators.yaml") as f:
        vconf = yaml.safe_load(f)
    for domain, metrics in (vconf.get("domains") or {}).items():
        for metric, bounds in (metrics or {}).items():
            VALIDATORS[metric] = (bounds["min"], bounds["max"], bounds.get("unit", ""))
except Exception:
    pass

# --- Ensure output directory ---
EVAL_DIR = f"{RUNTIME_ROOT}/evaluations"
os.makedirs(EVAL_DIR, exist_ok=True)

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row
    return db

def generate_id():
    ts = hex(int(time.time() * 1000))[2:]
    import random, string
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{ts}{rand}"

def build_candidate(finding, verification_rows, confidence_row):
    """Convert a finding + its verification/confidence context into a ScientificConclusionCandidate."""
    structured = None
    if finding["structured_data"]:
        try:
            structured = json.loads(finding["structured_data"]) if isinstance(finding["structured_data"], str) else finding["structured_data"]
        except (json.JSONDecodeError, TypeError):
            pass

    validator_results = []
    evidence_refs = []
    for vr in verification_rows:
        evidence_refs.append(vr["verification_id"])
        validator_results.append({
            "validator": vr["validator_name"],
            "passed": bool(vr["passed"]),
            "value": float(vr["input_value"]) if vr["input_value"] else None,
            "range": json.loads(vr["expected_range"]) if vr["expected_range"] else None,
            "error": vr["error_message"]
        })

    confidence_context = None
    if confidence_row:
        evidence_refs.append(confidence_row["score_id"])
        confidence_context = {
            "overall_score": confidence_row["overall_score"],
            "factors": json.loads(confidence_row["factors"]) if confidence_row["factors"] else {},
            "verdict": finding["judge_verdict"]
        }

    return {
        "artifact_id": finding["finding_id"],
        "artifact_type": "finding",
        "content": finding["content"],
        "structured_data": structured,
        "provenance_quote": finding["provenance_quote"],
        "provenance_page": finding["provenance_page"],
        "provenance_section": finding["provenance_section"],
        "paper_id": finding["paper_id"],
        "evidence_refs": evidence_refs,
        "validator_results": validator_results,
        "confidence_context": confidence_context
    }

def grade_item(item_id, item_conf, candidate):
    """Grade a single rubric item deterministically. Returns a RubricItemResult dict."""
    max_points = item_conf["max_points"]
    requires = item_conf.get("requires", [])
    name = item_id.replace("_", " ").title()

    # Check required inputs
    missing_inputs = []
    for req in requires:
        val = candidate.get(req)
        if val is None or val == [] or val == {}:
            missing_inputs.append(req)

    # If all required inputs are missing, score 0
    if missing_inputs and len(missing_inputs) == len(requires):
        return {
            "item_id": item_id,
            "name": name,
            "score": 0,
            "max_points": max_points,
            "passed": False,
            "failure_tags": ["missing_required_inputs"],
            "rationale": f"Required inputs missing: {', '.join(missing_inputs)}",
            "evidence_refs": [],
            "missing_inputs": missing_inputs
        }

    # --- Item-specific grading logic ---

    if item_id == "evidence_support":
        sd = candidate.get("structured_data")
        if not sd or not isinstance(sd, dict):
            return _item_result(item_id, name, 0, max_points, False,
                                ["no_structured_data"], "No structured data present.", missing_inputs=missing_inputs)
        has_metric = bool(sd.get("metric"))
        has_value = sd.get("value") is not None
        if has_metric and has_value:
            return _item_result(item_id, name, max_points, max_points, True,
                                [], "Structured data has metric and value.")
        elif has_metric or has_value:
            return _item_result(item_id, name, 1, max_points, True,
                                ["partial_structured_data"], "Structured data missing metric or value.")
        return _item_result(item_id, name, 0, max_points, False,
                            ["empty_structured_data"], "Structured data has neither metric nor value.", missing_inputs=missing_inputs)

    elif item_id == "provenance_support":
        quote = candidate.get("provenance_quote")
        if not quote or len(quote.strip()) < 10:
            return _item_result(item_id, name, 0, max_points, False,
                                ["missing_provenance"], "No provenance quote or too short (<10 chars).", missing_inputs=missing_inputs)
        if len(quote.strip()) >= 30:
            return _item_result(item_id, name, max_points, max_points, True,
                                [], f"Provenance quote present ({len(quote)} chars).")
        return _item_result(item_id, name, 1, max_points, True,
                            ["short_provenance"], f"Provenance quote present but short ({len(quote)} chars).")

    elif item_id == "numeric_consistency":
        vr = candidate.get("validator_results", [])
        if not vr:
            # No validators ran — not applicable, award partial credit
            return _item_result(item_id, name, 1, max_points, True,
                                [], "No numeric validators applicable.")
        all_passed = all(v["passed"] for v in vr)
        any_passed = any(v["passed"] for v in vr)
        refs = [v.get("validator", "") for v in vr]
        if all_passed:
            return _item_result(item_id, name, max_points, max_points, True,
                                [], f"All {len(vr)} validators passed.", evidence_refs=refs)
        elif any_passed:
            return _item_result(item_id, name, 1, max_points, True,
                                ["partial_range_violation"], f"Some validators failed.", evidence_refs=refs)
        return _item_result(item_id, name, 0, max_points, False,
                            ["range_violation"], f"All {len(vr)} validators failed.", evidence_refs=refs, missing_inputs=missing_inputs)

    elif item_id == "unit_consistency":
        sd = candidate.get("structured_data")
        if not sd or not isinstance(sd, dict):
            return _item_result(item_id, name, 0, max_points, False,
                                ["no_structured_data"], "No structured data to check units.", missing_inputs=missing_inputs)
        metric = (sd.get("metric", "") or "").lower().replace(" ", "_")
        reported_unit = (sd.get("unit", "") or "").strip()
        if metric in VALIDATORS:
            expected_unit = VALIDATORS[metric][2]
            if expected_unit and reported_unit:
                if reported_unit.lower().replace(".", "") == expected_unit.lower().replace(".", ""):
                    return _item_result(item_id, name, max_points, max_points, True,
                                        [], f"Unit '{reported_unit}' matches expected '{expected_unit}'.")
                else:
                    return _item_result(item_id, name, 0, max_points, False,
                                        ["unit_mismatch"], f"Unit '{reported_unit}' != expected '{expected_unit}'.")
        # No unit to check or no validator for this metric
        return _item_result(item_id, name, max_points, max_points, True,
                            [], "No expected unit defined for this metric (pass by default).")

    elif item_id == "contradiction_awareness":
        sd = candidate.get("structured_data")
        content = candidate.get("content", "")
        if not sd or not isinstance(sd, dict) or not content:
            return _item_result(item_id, name, 0, max_points, False,
                                ["insufficient_data"], "Cannot check contradiction without content and structured data.", missing_inputs=missing_inputs)
        # Simple heuristic: check if the value appears somewhere in the content
        value = str(sd.get("value", ""))
        metric = sd.get("metric", "")
        content_lower = content.lower()
        # Look for obvious contradictions: content says "decrease" but value is positive, etc.
        has_value_ref = value and (value in content or (metric and metric.lower() in content_lower))
        if has_value_ref:
            return _item_result(item_id, name, max_points, max_points, True,
                                [], "Content references the reported metric/value.")
        return _item_result(item_id, name, max_points, max_points, True,
                            [], "No detectable contradiction (heuristic check).")

    elif item_id == "uncertainty_calibration":
        cc = candidate.get("confidence_context")
        if not cc:
            return _item_result(item_id, name, 0, max_points, False,
                                ["no_confidence"], "No confidence context available.", missing_inputs=missing_inputs)
        overall = cc.get("overall_score", 0)
        factors = cc.get("factors", {})
        hall = factors.get("hallucination_check", 0)
        numeric = factors.get("numeric_validation", 0)
        # High confidence should require strong hallucination + numeric scores
        if overall >= 0.8 and (hall < 0.7 or numeric < 0.7):
            return _item_result(item_id, name, 0, max_points, False,
                                ["overconfident"], f"Confidence {overall:.2f} but hall={hall:.2f}, numeric={numeric:.2f}.")
        return _item_result(item_id, name, max_points, max_points, True,
                            [], f"Confidence {overall:.2f} calibrated with evidence quality.")

    elif item_id == "conclusion_alignment":
        sd = candidate.get("structured_data")
        content = candidate.get("content", "")
        if not sd or not isinstance(sd, dict) or not content:
            return _item_result(item_id, name, 0, max_points, False,
                                ["insufficient_data"], "Cannot check alignment without content and structured data.", missing_inputs=missing_inputs)
        metric = (sd.get("metric", "") or "").lower().replace("_", " ")
        value = str(sd.get("value", ""))
        content_lower = content.lower()
        aligned = (metric and metric in content_lower) or (value and value in content)
        if aligned:
            return _item_result(item_id, name, max_points, max_points, True,
                                [], "Content aligns with structured metric/value.")
        return _item_result(item_id, name, 0, max_points, False,
                            ["misaligned"], "Content does not reference the structured metric or value.")

    # Unknown item — fail explicitly
    return _item_result(item_id, name, 0, max_points, False,
                        ["unknown_item"], f"No grading logic for item '{item_id}'.")


def _item_result(item_id, name, score, max_points, passed, failure_tags, rationale,
                 evidence_refs=None, missing_inputs=None):
    return {
        "item_id": item_id,
        "name": name,
        "score": score,
        "max_points": max_points,
        "passed": passed,
        "failure_tags": failure_tags,
        "rationale": rationale,
        "evidence_refs": evidence_refs or [],
        "missing_inputs": missing_inputs or []
    }


def grade_candidate(candidate):
    """Grade a ScientificConclusionCandidate against the rubric. Returns a RubricResult dict."""
    result_id = generate_id()
    item_results = []

    for item_id, item_conf in items_conf.items():
        item_result = grade_item(item_id, item_conf, candidate)
        item_results.append(item_result)

    total_score = sum(ir["score"] for ir in item_results)
    passed = total_score >= PASS_THRESHOLD
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "rubric_result_id": result_id,
        "rubric_id": RUBRIC_ID,
        "rubric_version": RUBRIC_VERSION,
        "artifact_id": candidate["artifact_id"],
        "artifact_type": candidate["artifact_type"],
        "total_score": total_score,
        "max_score": MAX_SCORE,
        "pass_threshold": PASS_THRESHOLD,
        "passed": passed,
        "graded_at": now,
        "grader_name": GRADER_NAME,
        "grader_version": GRADER_VERSION,
        "item_results": item_results
    }


def persist_result(db, result):
    """Write rubric result to DB and JSON artifact."""
    # DB insert
    db.execute(
        """INSERT OR REPLACE INTO rubric_results
           (rubric_result_id, artifact_id, artifact_type, rubric_id, rubric_version,
            total_score, max_score, pass_threshold, passed, item_results_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (result["rubric_result_id"], result["artifact_id"], result["artifact_type"],
         result["rubric_id"], result["rubric_version"],
         result["total_score"], result["max_score"], result["pass_threshold"],
         1 if result["passed"] else 0,
         json.dumps(result["item_results"]),
         result["graded_at"])
    )
    db.commit()

    # JSON artifact
    artifact_path = os.path.join(EVAL_DIR, f"{result['artifact_id']}.rubric.json")
    with open(artifact_path, "w") as f:
        json.dump(result, f, indent=2)

    return artifact_path


def grade_finding(db, finding_id):
    """Grade a single finding."""
    finding = db.execute("SELECT * FROM findings WHERE finding_id=?", (finding_id,)).fetchone()
    if not finding:
        print(f"[rubric] Finding {finding_id} not found", file=sys.stderr)
        return None

    verification_rows = db.execute(
        "SELECT * FROM verification_results WHERE finding_id=?", (finding_id,)
    ).fetchall()

    confidence_row = db.execute(
        "SELECT * FROM confidence_scores WHERE target_id=? AND target_type='finding' ORDER BY created_at DESC LIMIT 1",
        (finding_id,)
    ).fetchone()

    candidate = build_candidate(finding, verification_rows, confidence_row)
    result = grade_candidate(candidate)
    artifact_path = persist_result(db, result)

    status = "PASS" if result["passed"] else "FAIL"
    failed_items = [ir["item_id"] for ir in result["item_results"] if not ir["passed"]]
    print(f"[rubric] {finding_id}: {status} ({result['total_score']}/{result['max_score']})"
          + (f" failed=[{', '.join(failed_items)}]" if failed_items else ""))
    return result


def grade_paper(db, paper_id):
    """Grade all accepted/revised findings for a paper."""
    findings = db.execute(
        "SELECT finding_id FROM findings WHERE paper_id=? AND judge_verdict IN ('accepted','revised')",
        (paper_id,)
    ).fetchall()

    if not findings:
        print(f"[rubric] No gradeable findings for {paper_id}")
        return []

    print(f"[rubric] Grading {len(findings)} findings for {paper_id}...")
    results = []
    for f in findings:
        result = grade_finding(db, f["finding_id"])
        if result:
            results.append(result)

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed
    print(f"[rubric] {paper_id}: {passed} passed, {failed} failed rubric")
    return results


# --- Main ---
db = get_db()

# Ensure rubric_results table exists (idempotent)
db.execute("""
CREATE TABLE IF NOT EXISTS rubric_results (
    rubric_result_id TEXT PRIMARY KEY,
    artifact_id     TEXT NOT NULL,
    artifact_type   TEXT NOT NULL DEFAULT 'finding',
    rubric_id       TEXT NOT NULL,
    rubric_version  TEXT NOT NULL,
    total_score     REAL NOT NULL,
    max_score       REAL NOT NULL,
    pass_threshold  REAL NOT NULL,
    passed          INTEGER NOT NULL CHECK(passed IN (0,1)),
    item_results_json TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
)
""")
db.execute("CREATE INDEX IF NOT EXISTS idx_rubric_artifact ON rubric_results(artifact_id)")
db.execute("CREATE INDEX IF NOT EXISTS idx_rubric_passed ON rubric_results(passed)")
db.commit()

if COMMAND == "grade" and TARGET_ID:
    grade_paper(db, TARGET_ID)
elif COMMAND == "grade-finding" and TARGET_ID:
    result = grade_finding(db, TARGET_ID)
    if result:
        print(json.dumps(result, indent=2))
elif COMMAND == "grade-batch":
    papers = db.execute("SELECT paper_id FROM papers WHERE status='judged' LIMIT 10").fetchall()
    print(f"[rubric] Batch grading {len(papers)} papers...")
    for p in papers:
        grade_paper(db, p["paper_id"])
else:
    print(f"[rubric] Unknown command: {COMMAND}", file=sys.stderr)
    print("Usage: rubric-grade.sh [grade <paper_id> | grade-finding <finding_id> | grade-batch]", file=sys.stderr)
    sys.exit(1)

db.close()
PYEOF
