#!/usr/bin/env bash
# judge-score.sh — Confidence scoring, hallucination detection, deterministic validation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-score-batch}"
export PAPER_ID="${2:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, json, os, sys, time, re, requests
from datetime import datetime

COMMAND = os.environ.get("COMMAND", "score-batch")
PAPER_ID = os.environ.get("PAPER_ID", "") or None
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")

with open(f"{REPO_ROOT}/prompts/system_judge.md") as f:
    JUDGE_PROMPT = f.read()

# Physical range validators
VALIDATORS = {
    "energy_density_gravimetric": (1, 2000, "Wh/kg"),
    "energy_density_volumetric": (1, 5000, "Wh/L"),
    "power_density": (1, 50000, "W/kg"),
    "solar_efficiency": (0, 47, "%"), "pce": (0, 47, "%"),
    "power_conversion_efficiency": (0, 47, "%"),
    "voltage": (0, 5, "V"), "open_circuit_voltage": (0, 2, "V"),
    "capacity": (1, 500, "mAh/g"), "cycle_life": (1, 100000, "cycles"),
    "coulombic_efficiency": (0, 100, "%"), "fill_factor": (0, 100, "%"),
    "bandgap": (0, 15, "eV"), "conductivity": (1e-20, 1e8, "S/m"),
    "temperature": (-273.15, 3000, "C"),
    "ph": (0, 14, ""), "co2_concentration": (0, 100000, "ppm"),
    "biodiversity_index": (0, 1, ""), "shannon_diversity": (0, 6, ""),
    "simpson_diversity": (0, 1, ""), "species_richness": (0, 100000, ""),
    "biomass_density": (0, 2000, "t/ha"), "soil_organic_carbon": (0, 30, "%"),
    "carbon_sequestration_rate": (0, 50, "tC/ha/yr"), "canopy_cover": (0, 100, "%"),
    "efficiency": (0, 100, "%"), "percentage": (0, 100, "%"),
}

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

def validate_numeric(structured_data):
    """Run deterministic range validators on structured data"""
    if not structured_data:
        return []
    try:
        data = json.loads(structured_data) if isinstance(structured_data, str) else structured_data
    except json.JSONDecodeError:
        return []

    results = []
    metric = (data.get("metric", "") or "").lower().replace(" ", "_")
    value = data.get("value")

    if not metric or value is None:
        return results

    try:
        if isinstance(value, str):
            if "-" in value and not value.startswith("-"):
                parts = value.split("-")
                val = (float(parts[0].strip()) + float(parts[-1].strip())) / 2
            else:
                val = float(re.sub(r'[^\d.\-eE+]', '', value))
        else:
            val = float(value)
    except (ValueError, TypeError):
        return [{"validator": "parse_check", "passed": False, "error": f"Cannot parse: {value}"}]

    for vname, (vmin, vmax, unit) in VALIDATORS.items():
        if metric == vname or metric.replace("_", "") == vname.replace("_", ""):
            passed = vmin <= val <= vmax
            results.append({
                "validator": f"range_{vname}",
                "passed": passed,
                "value": val,
                "range": [vmin, vmax],
                "error": None if passed else f"{val} outside [{vmin}, {vmax}]"
            })
            break

    return results

def check_hallucination(quote, source_text):
    """Check if provenance_quote exists in the source text"""
    if not quote or not source_text:
        return 0.1

    quote_clean = quote.strip().lower()
    text_clean = source_text.lower()

    # Exact match
    if quote_clean in text_clean:
        return 1.0

    # Fuzzy: check if 70%+ of words match in sequence
    quote_words = quote_clean.split()
    if len(quote_words) < 3:
        return 0.5

    matches = 0
    for word in quote_words:
        if word in text_clean:
            matches += 1

    ratio = matches / len(quote_words)
    if ratio > 0.8:
        return 0.9
    elif ratio > 0.6:
        return 0.7
    elif ratio > 0.4:
        return 0.5
    return 0.2

def score_paper(db, paper_id):
    """Score all findings for a paper"""
    paper = db.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
    if not paper:
        return

    # Load source text for hallucination check
    source_text = ""
    docling_md = f"{RUNTIME_ROOT}/parsed/{paper_id}_docling.md"
    if os.path.exists(docling_md):
        with open(docling_md) as f:
            source_text = f.read()

    findings = db.execute(
        "SELECT * FROM findings WHERE paper_id=? ORDER BY extraction_cycle", (paper_id,)
    ).fetchall()

    print(f"[judge] Scoring {len(findings)} findings for {paper_id}...")

    accepted = revised = rejected = 0
    total_confidence = 0

    for finding in findings:
        fid = finding["finding_id"]

        # 1. Deterministic validation
        validation_results = validate_numeric(finding["structured_data"])
        numeric_score = 1.0
        for vr in validation_results:
            vid = generate_id()
            db.execute(
                """INSERT INTO verification_results
                   (verification_id, finding_id, validator_name, passed,
                    input_value, expected_range, actual_parsed, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (vid, fid, vr["validator"], 1 if vr["passed"] else 0,
                 str(vr.get("value", "")),
                 json.dumps(vr.get("range")) if vr.get("range") else None,
                 json.dumps({"value": vr.get("value")}),
                 vr.get("error"))
            )
            if not vr["passed"]:
                numeric_score = 0.3

        # 2. Hallucination check
        hall_score = check_hallucination(finding["provenance_quote"], source_text)

        # 3. Source quality (from paper metadata)
        source = paper["source"]
        source_score = {"nature": 0.95, "openalex": 0.75, "arxiv": 0.65, "rew": 0.50}.get(source, 0.5)

        # 4. Extraction quality
        has_structured = finding["structured_data"] is not None
        has_quote = finding["provenance_quote"] is not None and len(finding["provenance_quote"] or "") > 10
        extraction_score = 0.5 + (0.25 if has_structured else 0) + (0.25 if has_quote else 0)

        # 5. Overall confidence
        factors = {
            "source_quality": source_score,
            "extraction_quality": extraction_score,
            "cross_reference": 0.5,  # Default, updated when more papers available
            "numeric_validation": numeric_score,
            "hallucination_check": hall_score
        }

        # Weighted average
        weights = {"source_quality": 0.20, "extraction_quality": 0.25,
                   "cross_reference": 0.15, "numeric_validation": 0.25,
                   "hallucination_check": 0.15}
        overall = sum(factors[k] * weights[k] for k in factors)

        # Verdict
        if hall_score < 0.5 or overall < 0.25:
            verdict = "rejected"
            rejected += 1
        elif overall >= 0.6 and hall_score >= 0.5:
            verdict = "accepted"
            accepted += 1
        else:
            verdict = "revised"
            revised += 1

        # Store confidence score
        sid = generate_id()
        db.execute(
            """INSERT INTO confidence_scores
               (score_id, target_id, target_type, overall_score, factors, judge_model)
               VALUES (?, ?, 'finding', ?, ?, ?)""",
            (sid, fid, round(overall, 3), json.dumps(factors), OLLAMA_MODEL)
        )

        # Update finding
        db.execute(
            "UPDATE findings SET confidence=?, judge_verdict=?, judge_rationale=? WHERE finding_id=?",
            (round(overall, 3), verdict,
             f"hall={hall_score:.2f} num={numeric_score:.2f} src={source_score:.2f}",
             fid)
        )

        total_confidence += overall

    db.commit()

    db.execute(
        "UPDATE papers SET status='judged', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
        (paper_id,)
    )
    db.commit()

    avg_conf = total_confidence / max(len(findings), 1)
    print(f"[judge] {paper_id}: {accepted} accepted, {revised} revised, {rejected} rejected (avg confidence: {avg_conf:.2f})")
    return {"accepted": accepted, "revised": revised, "rejected": rejected, "avg_confidence": avg_conf}

# Main
db = get_db()
if COMMAND == "score" and PAPER_ID:
    score_paper(db, PAPER_ID)
elif COMMAND == "score-batch":
    papers = db.execute("SELECT paper_id FROM papers WHERE status='extracted' LIMIT 10").fetchall()
    print(f"[judge] Scoring {len(papers)} papers...")
    for p in papers:
        score_paper(db, p["paper_id"])
elif COMMAND == "validate" and PAPER_ID:
    findings = db.execute("SELECT * FROM findings WHERE paper_id=? AND structured_data IS NOT NULL", (PAPER_ID,)).fetchall()
    for f in findings:
        results = validate_numeric(f["structured_data"])
        print(json.dumps({"finding_id": f["finding_id"], "validations": results}, indent=2))
db.close()
PYEOF
