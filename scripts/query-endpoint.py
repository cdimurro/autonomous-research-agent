#!/usr/bin/env python3
"""query-endpoint.py — Flask microservice for SQLite queries (localhost:8099)"""

import os
os.environ["FLASK_SKIP_DOTENV"] = "1"

import sys
import json
import sqlite3
import sqlite_vec
from flask import Flask, request, jsonify
from functools import wraps

app = Flask(__name__)

RUNTIME_ROOT = os.environ.get("SCIRES_RUNTIME_ROOT",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime"))
DB_PATH = os.path.join(RUNTIME_ROOT, "db", "scires.db")
API_KEY = os.environ.get("SCIRES_API_KEY")
PORT = int(os.environ.get("SCIRES_QUERY_PORT", 8099))

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.row_factory = sqlite3.Row
    return db

def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_KEY:
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if token != API_KEY:
                return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/health")
def health():
    db = None
    try:
        db = get_db()
        total = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        return jsonify({"status": "ok", "total_papers": total})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    finally:
        if db:
            db.close()

@app.route("/papers")
@auth_required
def papers():
    db = None
    try:
        status = request.args.get("status")
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = int(request.args.get("offset", 0))

        db = get_db()
        query = "SELECT paper_id, title, source, status, relevance_score, publication_date, fetched_at FROM papers"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY fetched_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = db.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        if db:
            db.close()

@app.route("/findings")
@auth_required
def findings():
    db = None
    try:
        paper_id = request.args.get("paper_id")
        min_confidence = float(request.args.get("min_confidence", 0))
        finding_type = request.args.get("type")
        limit = min(int(request.args.get("limit", 50)), 200)

        db = get_db()
        query = "SELECT * FROM findings WHERE 1=1"
        params = []

        if paper_id:
            query += " AND paper_id = ?"
            params.append(paper_id)
        if min_confidence > 0:
            query += " AND confidence >= ?"
            params.append(min_confidence)
        if finding_type:
            query += " AND finding_type = ?"
            params.append(finding_type)

        query += " ORDER BY confidence DESC LIMIT ?"
        params.append(limit)

        rows = db.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        if db:
            db.close()

@app.route("/hypotheses")
@auth_required
def hypotheses():
    db = None
    try:
        status = request.args.get("status")
        limit = min(int(request.args.get("limit", 20)), 100)

        db = get_db()
        query = "SELECT * FROM hypotheses"
        params = []

        if status:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY confidence DESC LIMIT ?"
        params.append(limit)

        rows = db.execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        if db:
            db.close()

@app.route("/search")
@auth_required
def search():
    q = request.args.get("q", "")
    search_type = request.args.get("type", "text")
    limit = min(int(request.args.get("limit", 10)), 50)

    if not q:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    db = None
    try:
        db = get_db()

        if search_type == "text":
            rows = db.execute("""
                SELECT paper_id, title, abstract, source, status
                FROM papers
                WHERE title LIKE ? OR abstract LIKE ?
                LIMIT ?
            """, (f"%{q}%", f"%{q}%", limit)).fetchall()
            return jsonify([dict(r) for r in rows])

        elif search_type == "vector":
            import numpy as np
            from transformers import AutoTokenizer
            from adapters import AutoAdapterModel
            import torch

            tokenizer = AutoTokenizer.from_pretrained("allenai/specter2_base")
            model = AutoAdapterModel.from_pretrained("allenai/specter2_base")
            model.load_adapter("allenai/specter2", source="hf", load_as="proximity", set_active=True)
            model.eval()

            inputs = tokenizer(q, return_tensors="pt", padding=True, truncation=True, max_length=512)
            with torch.no_grad():
                outputs = model(**inputs)
            emb = outputs.last_hidden_state[:, 0, :].squeeze().numpy().astype(np.float32)

            results = db.execute("""
                SELECT paper_id, distance FROM paper_embeddings
                WHERE embedding MATCH ?
                ORDER BY distance LIMIT ?
            """, (emb.tobytes(), limit)).fetchall()

            output = []
            for r in results:
                meta = db.execute("SELECT title, source FROM papers WHERE paper_id=?",
                                 (r["paper_id"],)).fetchone()
                output.append({
                    "paper_id": r["paper_id"],
                    "distance": r["distance"],
                    "title": meta["title"] if meta else None,
                    "source": meta["source"] if meta else None
                })
            return jsonify(output)

        return jsonify({"error": f"Unknown search type: {search_type}"}), 400
    except Exception as e:
        return jsonify({"error": f"Search failed: {e}"}), 500
    finally:
        if db:
            db.close()

@app.route("/graph")
@auth_required
def graph():
    entity = request.args.get("entity", "")
    hops = min(int(request.args.get("hops", 2)), 3)

    if not entity:
        return jsonify({"error": "Missing 'entity' parameter"}), 400

    db = None
    try:
        db = get_db()
        ent = db.execute(
            "SELECT * FROM entities WHERE canonical_name=? OR name LIKE ? LIMIT 1",
            (entity.lower(), f"%{entity}%")
        ).fetchone()

        if not ent:
            return jsonify({"error": f"Entity '{entity}' not found"}), 404

        eid = ent["entity_id"]
        rels = db.execute("""
            SELECT r.relation_type, r.confidence, e2.name as target, e2.entity_type
            FROM relations r
            JOIN entities e2 ON r.target_id = e2.entity_id AND r.target_type = 'entity'
            WHERE r.source_id = ? AND r.source_type = 'entity'
            ORDER BY r.confidence DESC
        """, (eid,)).fetchall()

        return jsonify({
            "entity": dict(ent),
            "relations": [dict(r) for r in rels]
        })
    finally:
        if db:
            db.close()

@app.route("/stats")
@auth_required
def stats():
    db = None
    try:
        db = get_db()
        result = {
            "papers": {r["status"]: r["cnt"] for r in
                       db.execute("SELECT status, COUNT(*) as cnt FROM papers GROUP BY status").fetchall()},
            "findings": db.execute("SELECT COUNT(*) FROM findings").fetchone()[0],
            "findings_accepted": db.execute("SELECT COUNT(*) FROM findings WHERE judge_verdict='accepted'").fetchone()[0],
            "entities": db.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "hypotheses": db.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0],
            "relations": db.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
        }
        return jsonify(result)
    finally:
        if db:
            db.close()

if __name__ == "__main__":
    import werkzeug.serving
    print(f"[query-endpoint] Starting on localhost:{PORT}")
    server = werkzeug.serving.make_server("127.0.0.1", PORT, app, threaded=True)
    server.serve_forever()
