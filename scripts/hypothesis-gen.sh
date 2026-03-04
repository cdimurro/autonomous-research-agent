#!/usr/bin/env bash
# hypothesis-gen.sh — Generate hypotheses from accumulated findings
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-generate}"
export EXTRA_ARG="${2:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, json, os, sys, time, requests
from datetime import datetime, timedelta

COMMAND = os.environ.get("COMMAND", "generate")
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")

with open(f"{REPO_ROOT}/prompts/system_hypothesis.md") as f:
    HYPOTHESIS_PROMPT = f.read()

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

def call_ollama(system_prompt, user_message, temperature=0.7, max_tokens=4096):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "/no_think\n" + user_message}
        ],
        "stream": False,
        "options": {"num_predict": max_tokens, "num_ctx": 16384, "temperature": temperature}
    }
    for attempt in range(3):
        try:
            resp = requests.post(f"http://{OLLAMA_HOST}/api/chat", json=payload, timeout=300)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                raise

def parse_json(text):
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return None

db = get_db()

if COMMAND == "generate":
    domain = None
    extra_arg = os.environ.get("EXTRA_ARG", "")
    if extra_arg.startswith("--domain="):
        domain = extra_arg.split("=")[1]

    # Gather recent high-confidence findings
    cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = """
        SELECT f.finding_id, f.content, f.finding_type, f.confidence,
               f.structured_data, p.title, p.source
        FROM findings f
        JOIN papers p ON f.paper_id = p.paper_id
        WHERE f.judge_verdict = 'accepted' AND f.confidence >= 0.6
        AND f.created_at >= ?
        ORDER BY f.confidence DESC
        LIMIT 30
    """
    findings = db.execute(query, (cutoff,)).fetchall()

    if not findings:
        print("[hypothesis] No recent high-confidence findings available")
        sys.exit(0)

    # Format findings for LLM
    findings_text = ""
    for f in findings:
        findings_text += f"\n- [{f['finding_id'][:12]}] ({f['finding_type']}, conf={f['confidence']:.2f}) {f['content'][:200]}"
        if f['structured_data']:
            findings_text += f" | Data: {f['structured_data'][:100]}"
        findings_text += f" [Source: {f['title'][:50]}]"

    # Get existing hypotheses for context
    existing = db.execute("SELECT hypothesis, status FROM hypotheses ORDER BY created_at DESC LIMIT 10").fetchall()
    existing_text = ""
    for h in existing:
        existing_text += f"\n- [{h['status']}] {h['hypothesis'][:150]}"

    user_message = f"""Recent findings (last 7 days, confidence >= 0.6):
{findings_text}

Existing hypotheses (for reference, avoid duplicates):
{existing_text if existing_text else "None yet."}

Generate 2-3 novel hypotheses based on these findings. Focus on cross-paper connections and testable predictions."""

    if domain:
        user_message += f"\n\nFocus on domain: {domain}"

    print(f"[hypothesis] Generating hypotheses from {len(findings)} findings...")
    response = call_ollama(HYPOTHESIS_PROMPT, user_message)
    result = parse_json(response)

    if not result or "hypotheses" not in result:
        print(f"[hypothesis] Failed to parse response", file=sys.stderr)
        debug_path = f"{RUNTIME_ROOT}/extractions/hypothesis_raw.txt"
        with open(debug_path, "w") as f:
            f.write(response)
        sys.exit(1)

    run_id = f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_hyp"

    for hyp in result["hypotheses"]:
        hid = generate_id()
        db.execute(
            """INSERT INTO hypotheses
               (hypothesis_id, hypothesis, domain, evidence_ids, confidence,
                status, critique_log, generated_from)
               VALUES (?, ?, ?, ?, ?, 'proposed', ?, ?)""",
            (hid,
             hyp.get("hypothesis", ""),
             hyp.get("domain", domain or "cross-domain"),
             json.dumps(hyp.get("supporting_evidence", [])),
             hyp.get("confidence", 0.5),
             json.dumps([{
                 "cycle": 1,
                 "critique": hyp.get("critique", ""),
                 "reformulation": hyp.get("reformulation"),
                 "timestamp": datetime.utcnow().isoformat()
             }]),
             run_id)
        )
        print(f"  [hypothesis] {hid[:12]}: {hyp.get('hypothesis', '')[:100]} (conf={hyp.get('confidence', 0.5):.2f})")

    db.commit()
    print(f"\n[hypothesis] Generated {len(result['hypotheses'])} hypotheses")

elif COMMAND == "evaluate":
    hypotheses = db.execute(
        "SELECT * FROM hypotheses WHERE status IN ('proposed', 'under_review') ORDER BY created_at"
    ).fetchall()
    print(f"[hypothesis] Evaluating {len(hypotheses)} hypotheses...")
    for h in hypotheses:
        print(f"  [{h['status']}] {h['hypothesis'][:100]} (conf={h['confidence']:.2f})")

elif COMMAND == "list":
    status_filter = None
    extra_arg = os.environ.get("EXTRA_ARG", "")
    if extra_arg.startswith("--status="):
        status_filter = extra_arg.split("=")[1]

    query = "SELECT * FROM hypotheses"
    params = []
    if status_filter:
        query += " WHERE status = ?"
        params.append(status_filter)
    query += " ORDER BY confidence DESC"

    hypotheses = db.execute(query, params).fetchall()
    output = [dict(h) for h in hypotheses]
    print(json.dumps(output, indent=2))

db.close()
PYEOF
