#!/usr/bin/env bash
# embed-index.sh — Generate SPECTER2 embeddings and index into sqlite-vec
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-index-batch}"
export PAPER_ID="${2:-}"
export SEARCH_TYPE="${3:-paper}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, sqlite_vec, json, os, sys, struct
import numpy as np

COMMAND = os.environ.get("COMMAND", "index-batch")
PAPER_ID = os.environ.get("PAPER_ID", "") or None
QUERY = PAPER_ID if COMMAND == "search" else None
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"

# Lazy-load SPECTER2 model
_model = None
_tokenizer = None

def get_model():
    global _model, _tokenizer
    if _model is None:
        print("[embed] Loading SPECTER2 model...")
        from transformers import AutoTokenizer
        from adapters import AutoAdapterModel

        _tokenizer = AutoTokenizer.from_pretrained("allenai/specter2_base")
        _model = AutoAdapterModel.from_pretrained("allenai/specter2_base")
        _model.load_adapter("allenai/specter2", source="hf", load_as="proximity", set_active=True)
        _model.eval()
        print("[embed] SPECTER2 loaded (768-dim)")
    return _model, _tokenizer

def embed_text(text, max_length=512):
    """Generate SPECTER2 embedding for text"""
    import torch
    model, tokenizer = get_model()
    inputs = tokenizer(text, return_tensors="pt", padding=True,
                       truncation=True, max_length=max_length)
    with torch.no_grad():
        outputs = model(**inputs)
    # Use CLS token embedding
    embedding = outputs.last_hidden_state[:, 0, :].squeeze().numpy()
    return embedding.astype(np.float32)

def serialize_embedding(emb):
    """Serialize numpy array to bytes for sqlite-vec"""
    return emb.tobytes()

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row
    return db

def index_paper(db, paper_id):
    """Generate and store embeddings for a paper and its findings"""
    paper = db.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
    if not paper:
        return

    # Paper embedding (title + abstract)
    text = f"{paper['title']} {paper['abstract'] or ''}"
    emb = embed_text(text)
    try:
        db.execute("INSERT INTO paper_embeddings (paper_id, embedding) VALUES (?, ?)",
                   (paper_id, serialize_embedding(emb)))
    except sqlite3.IntegrityError:
        db.execute("UPDATE paper_embeddings SET embedding=? WHERE paper_id=?",
                   (serialize_embedding(emb), paper_id))

    # Finding embeddings
    findings = db.execute(
        "SELECT finding_id, content FROM findings WHERE paper_id=? AND judge_verdict='accepted'",
        (paper_id,)
    ).fetchall()

    for f in findings:
        femb = embed_text(f["content"])
        try:
            db.execute("INSERT INTO finding_embeddings (finding_id, embedding) VALUES (?, ?)",
                       (f["finding_id"], serialize_embedding(femb)))
        except sqlite3.IntegrityError:
            pass

    # Entity embeddings
    entities = db.execute(
        "SELECT entity_id, name, entity_type FROM entities WHERE paper_id=?",
        (paper_id,)
    ).fetchall()

    for e in entities:
        eemb = embed_text(f"{e['name']} ({e['entity_type']})")
        try:
            db.execute("INSERT INTO entity_embeddings (entity_id, embedding) VALUES (?, ?)",
                       (e["entity_id"], serialize_embedding(eemb)))
        except sqlite3.IntegrityError:
            pass

    db.commit()

    # Update status
    db.execute(
        "UPDATE papers SET status='indexed', updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE paper_id=?",
        (paper_id,)
    )
    db.commit()

    print(f"[embed] {paper_id}: indexed (1 paper + {len(findings)} findings + {len(entities)} entities)")

def search_similar(db, query, search_type="paper", limit=10):
    """Vector similarity search"""
    query_emb = embed_text(query)

    table = {
        "paper": ("paper_embeddings", "paper_id"),
        "finding": ("finding_embeddings", "finding_id"),
        "entity": ("entity_embeddings", "entity_id")
    }.get(search_type, ("paper_embeddings", "paper_id"))

    results = db.execute(f"""
        SELECT {table[1]}, distance
        FROM {table[0]}
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
    """, (serialize_embedding(query_emb), limit)).fetchall()

    output = []
    for r in results:
        item_id = r[table[1]]
        distance = r["distance"]

        # Get metadata
        if search_type == "paper":
            meta = db.execute("SELECT title, source, status FROM papers WHERE paper_id=?", (item_id,)).fetchone()
        elif search_type == "finding":
            meta = db.execute("SELECT content, confidence, finding_type FROM findings WHERE finding_id=?", (item_id,)).fetchone()
        else:
            meta = db.execute("SELECT name, entity_type FROM entities WHERE entity_id=?", (item_id,)).fetchone()

        output.append({
            "id": item_id,
            "distance": distance,
            "metadata": dict(meta) if meta else None
        })

    return output

# Main
db = get_db()

if COMMAND == "index" and PAPER_ID:
    index_paper(db, PAPER_ID)
elif COMMAND == "index-batch":
    papers = db.execute("SELECT paper_id FROM papers WHERE status='aligned' LIMIT 10").fetchall()
    print(f"[embed] Indexing {len(papers)} papers...")
    succeeded = 0
    for p in papers:
        try:
            index_paper(db, p["paper_id"])
            succeeded += 1
        except Exception as e:
            print(f"[embed] Error indexing {p['paper_id']}: {e}", file=sys.stderr)
    print(f"[embed] Batch complete: {succeeded}/{len(papers)} succeeded")
    db.close()
    if len(papers) > 0 and succeeded == 0:
        sys.exit(1)
    sys.exit(0)
elif COMMAND == "search" and QUERY:
    search_type_env = os.environ.get("SEARCH_TYPE", "paper")
    search_type = search_type_env.split("=")[1] if "=" in search_type_env else search_type_env
    results = search_similar(db, QUERY, search_type)
    print(json.dumps(results, indent=2, default=str))

db.close()
PYEOF
