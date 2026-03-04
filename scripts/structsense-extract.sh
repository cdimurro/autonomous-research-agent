#!/usr/bin/env bash
# structsense-extract.sh — LLM-driven structured extraction of findings, entities, relations
# Usage: structsense-extract.sh extract <paper_id> | extract-batch
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-extract-batch}"
export PAPER_ID="${2:-}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3
import json
import os
import sys
import time
import requests
import yaml
from datetime import datetime
from pathlib import Path

COMMAND = os.environ.get("COMMAND", "extract-batch")
PAPER_ID = os.environ.get("PAPER_ID", "") or None
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
REPO_ROOT = os.environ["SCIRES_REPO_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")

# Load system prompt
with open(f"{REPO_ROOT}/prompts/system_extractor.md") as f:
    SYSTEM_PROMPT = f.read()

# Load model params from config/models.yaml
EXTRACT_TEMPERATURE = 0.2
EXTRACT_MAX_TOKENS = 8192
EXTRACT_NUM_CTX = 16384
try:
    with open(f"{REPO_ROOT}/config/models.yaml") as f:
        mconf = yaml.safe_load(f) or {}
    ext = (mconf.get("routing") or {}).get("by_task_type", {}).get("extraction", {})
    EXTRACT_TEMPERATURE = float(ext.get("temperature", EXTRACT_TEMPERATURE))
    EXTRACT_MAX_TOKENS = int(ext.get("max_tokens", EXTRACT_MAX_TOKENS))
    for prov in (mconf.get("providers") or {}).values():
        for m in (prov.get("models") or {}).values():
            if m.get("role") == "primary":
                EXTRACT_NUM_CTX = int(m.get("context_window", EXTRACT_NUM_CTX))
except Exception as e:
    print(f"[structsense] Warning: Could not load models.yaml ({e}), using defaults", file=sys.stderr)

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

def call_ollama(system_prompt, user_message, temperature=None, max_tokens=None):
    """Call Ollama chat API"""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "/no_think\n" + user_message}
        ],
        "stream": False,
        "options": {
            "num_predict": max_tokens or EXTRACT_MAX_TOKENS,
            "num_ctx": EXTRACT_NUM_CTX,
            "temperature": temperature if temperature is not None else EXTRACT_TEMPERATURE
        }
    }

    for attempt in range(3):
        try:
            resp = requests.post(
                f"http://{OLLAMA_HOST}/api/chat",
                json=payload,
                timeout=600
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            return content, tokens
        except Exception as e:
            if attempt < 2:
                wait = 2 ** (attempt + 1)
                print(f"[structsense] Retry {attempt+1}/3 after {wait}s: {e}", file=sys.stderr)
                time.sleep(wait)
            else:
                raise

def load_parsed_text(paper_id):
    """Load the best parsed text for a paper"""
    # Prefer Docling markdown, fall back to GROBID XML text
    docling_md = f"{RUNTIME_ROOT}/parsed/{paper_id}_docling.md"
    if os.path.exists(docling_md):
        with open(docling_md) as f:
            return f.read()

    grobid_xml = f"{RUNTIME_ROOT}/parsed/{paper_id}_grobid.xml"
    if os.path.exists(grobid_xml):
        from lxml import etree
        ns = {"tei": "http://www.tei-c.org/ns/1.0"}
        root = etree.parse(grobid_xml).getroot()
        body = root.find(".//tei:body", ns)
        if body is not None:
            return " ".join(body.itertext()).strip()

    return None

def parse_llm_json(text):
    """Extract JSON from LLM response (may contain markdown fences)"""
    # Strip markdown code fences
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        # Try to find JSON object in text
        import re
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None

def extract_paper(db, paper_id, cycle=1):
    """Run STRUCTSENSE extraction on a paper"""
    parsed_text = load_parsed_text(paper_id)
    if not parsed_text:
        print(f"[structsense] {paper_id}: No parsed text available", file=sys.stderr)
        return False

    # Truncate to fit context window — keep under 12k chars for reasonable inference time
    if len(parsed_text) > 12000:
        parsed_text = parsed_text[:12000] + "\n\n[TRUNCATED]"

    paper = db.execute("SELECT title, abstract FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
    title = paper["title"] if paper else ""
    abstract = paper["abstract"] or "" if paper else ""

    user_message = f"""Paper Title: {title}

Abstract: {abstract}

Full Text:
{parsed_text}

Extract all findings, entities, and relations from this paper. Remember: every finding MUST include a verbatim provenance_quote from the text above."""

    # Append feedback context if available (set by feedback-loop.sh)
    feedback_ctx = os.environ.get("SCIRES_FEEDBACK_CONTEXT", "")
    if feedback_ctx:
        user_message += f"\n\nPrevious extraction feedback:\n{feedback_ctx}"

    print(f"[structsense] {paper_id}: Extracting (cycle {cycle}, {len(parsed_text)} chars)...")
    db.execute("UPDATE papers SET status='extracting', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?", (paper_id,))
    db.commit()

    start_time = time.time()
    try:
        response_text, tokens_used = call_ollama(SYSTEM_PROMPT, user_message)
    except Exception as e:
        db.execute(
            "UPDATE papers SET status='failed', error_message=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
            (str(e), paper_id)
        )
        db.commit()
        return False

    duration_ms = int((time.time() - start_time) * 1000)

    # Parse response
    extraction = parse_llm_json(response_text)
    if not extraction:
        # Save raw response for debugging
        debug_path = f"{RUNTIME_ROOT}/extractions/{paper_id}_raw_cycle{cycle}.txt"
        with open(debug_path, "w") as f:
            f.write(response_text)
        print(f"[structsense] {paper_id}: Failed to parse JSON response (saved to {debug_path})", file=sys.stderr)
        if cycle == 1:
            db.execute(
                "UPDATE papers SET status='failed', error_message='LLM output not valid JSON', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
                (paper_id,)
            )
            db.commit()
        return False

    # Save extraction bundle
    bundle_path = f"{RUNTIME_ROOT}/extractions/{paper_id}_cycle{cycle}.json"
    with open(bundle_path, "w") as f:
        json.dump(extraction, f, indent=2)

    # Normalize field names (LLM may use different keys)
    VALID_FINDING_TYPES = {'result','method','material','metric','claim','limitation','future_work','comparison'}
    VALID_ENTITY_TYPES = {'material','method','metric','organism','ecosystem','chemical','device','institution','dataset','software'}
    VALID_RELATION_TYPES = {'uses','measures','improves_on','contradicts','supports','cites','part_of','produces','degrades','contains','equivalent_to'}

    def normalize_finding_type(t):
        t = (t or "claim").lower().strip()
        if t in VALID_FINDING_TYPES: return t
        return "claim"

    def normalize_entity_type(t):
        t = (t or "material").lower().strip().replace("/", "_").replace(" ", "_")
        if t in VALID_ENTITY_TYPES: return t
        # Map common alternatives
        for valid in VALID_ENTITY_TYPES:
            if valid in t or t in valid: return valid
        return "material"

    def normalize_relation_type(t):
        t = (t or "uses").lower().strip()
        if t in VALID_RELATION_TYPES: return t
        return "uses"

    # Insert findings
    findings_count = 0
    for finding in extraction.get("findings", []):
        fid = generate_id()
        # Flexible field mapping
        content = finding.get("content") or finding.get("title") or finding.get("description") or ""
        prov_quote = finding.get("provenance_quote") or finding.get("quote") or finding.get("evidence") or ""
        ftype = normalize_finding_type(finding.get("finding_type") or finding.get("type"))
        confidence = float(finding.get("confidence", 0.5))
        if confidence > 1: confidence = confidence / 100.0  # Handle percentage
        prov_page = finding.get("provenance_page") or finding.get("page")
        prov_section = finding.get("provenance_section") or finding.get("section")
        structured = finding.get("structured_data")

        try:
            db.execute(
                """INSERT INTO findings (finding_id, paper_id, finding_type, content,
                   structured_data, confidence, provenance_page, provenance_section,
                   provenance_quote, extraction_cycle)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fid, paper_id, ftype, content,
                 json.dumps(structured) if structured else None,
                 confidence, prov_page, prov_section, prov_quote, cycle)
            )
            findings_count += 1
        except Exception as e:
            print(f"[structsense] Error inserting finding: {e}", file=sys.stderr)

    # Insert entities
    entities_count = 0
    for entity in extraction.get("entities", []):
        eid = generate_id()
        name = entity.get("name") or entity.get("entity") or ""
        etype = normalize_entity_type(entity.get("entity_type") or entity.get("type"))
        try:
            db.execute(
                """INSERT INTO entities (entity_id, name, canonical_name, entity_type,
                   paper_id, section, properties)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (eid, name, name.lower(), etype, paper_id,
                 entity.get("section"),
                 json.dumps(entity.get("properties") or entity.get("description")) if (entity.get("properties") or entity.get("description")) else None)
            )
            entities_count += 1
        except Exception as e:
            print(f"[structsense] Error inserting entity: {e}", file=sys.stderr)

    # Insert relations
    relations_count = 0
    for rel in extraction.get("relations", []):
        rid = generate_id()
        source = str(rel.get("source") or rel.get("subject_entity_id") or rel.get("source_id") or "")
        target = str(rel.get("target") or rel.get("object_entity_id") or rel.get("target_id") or "")
        rtype = normalize_relation_type(rel.get("relation_type") or rel.get("predicate") or rel.get("type"))
        try:
            db.execute(
                """INSERT INTO relations (relation_id, source_id, source_type,
                   target_id, target_type, relation_type, confidence, paper_id)
                   VALUES (?, ?, 'entity', ?, 'entity', ?, ?, ?)""",
                (rid, source, target, rtype,
                 float(rel.get("confidence", 0.5)),
                 paper_id)
            )
            relations_count += 1
        except Exception as e:
            print(f"[structsense] Error inserting relation: {e}", file=sys.stderr)

    db.commit()

    # Log run
    run_id = f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{paper_id[:8]}"
    db.execute(
        """INSERT INTO runs (run_id, task_type, status, papers_processed,
           findings_produced, tokens_used, duration_ms, completed_at)
           VALUES (?, 'extract', 'completed', 1, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))""",
        (run_id, findings_count, tokens_used, duration_ms)
    )
    db.commit()

    if cycle == 1:
        db.execute("UPDATE papers SET status='extracted', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?", (paper_id,))
        db.commit()

    print(f"[structsense] {paper_id} cycle {cycle}: {findings_count} findings, {entities_count} entities, {relations_count} relations ({tokens_used} tokens, {duration_ms}ms)")
    return True

# Main
db = get_db()

if COMMAND == "extract" and PAPER_ID:
    extract_paper(db, PAPER_ID)
elif COMMAND == "extract-batch":
    papers = db.execute("SELECT paper_id FROM papers WHERE status='parsed' LIMIT 5").fetchall()
    print(f"[structsense] Processing {len(papers)} papers...")
    succeeded = 0
    for paper in papers:
        if extract_paper(db, paper["paper_id"]):
            succeeded += 1
    print(f"[structsense] Batch complete: {succeeded}/{len(papers)} succeeded")
    db.close()
    if len(papers) > 0 and succeeded == 0:
        sys.exit(1)
    sys.exit(0)
else:
    print("Usage: structsense-extract.sh extract <paper_id> | extract-batch", file=sys.stderr)

db.close()
PYEOF
