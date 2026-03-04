#!/usr/bin/env bash
# graph-build.sh — Build knowledge graph from entities and relations
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$SCRIPT_DIR/.env"

export COMMAND="${1:-build}"
export ARG="${2:-}"
export HOPS="${3:-2}"
PYTHON="${SCIRES_VENV}/bin/python3"

"$PYTHON" << 'PYEOF'
import sqlite3, json, os, sys

COMMAND = os.environ.get("COMMAND", "build")
ARG = os.environ.get("ARG", "") or None
RUNTIME_ROOT = os.environ["SCIRES_RUNTIME_ROOT"]
DB_PATH = f"{RUNTIME_ROOT}/db/scires.db"

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row
    return db

db = get_db()

if COMMAND == "build" and ARG:
    # Build graph for a single paper (already done during extraction)
    paper_id = ARG
    entities = db.execute("SELECT COUNT(*) as cnt FROM entities WHERE paper_id=?", (paper_id,)).fetchone()["cnt"]
    relations = db.execute("SELECT COUNT(*) as cnt FROM relations WHERE paper_id=?", (paper_id,)).fetchone()["cnt"]
    print(json.dumps({"paper_id": paper_id, "entities": entities, "relations": relations}))

elif COMMAND == "query" and ARG:
    entity_name = ARG
    hops_env = os.environ.get("HOPS", "2")
    hops = int(hops_env.split("=")[1]) if "=" in hops_env else int(hops_env)

    # Find entity
    entity = db.execute(
        "SELECT * FROM entities WHERE canonical_name=? OR name LIKE ?",
        (entity_name.lower(), f"%{entity_name}%")
    ).fetchone()

    if not entity:
        print(json.dumps({"error": f"Entity '{entity_name}' not found"}))
        sys.exit(0)

    eid = entity["entity_id"]
    print(f"[graph] Querying {hops}-hop neighborhood for {entity['name']}...")

    # Direct relations
    outgoing = db.execute("""
        SELECT r.relation_type, r.confidence, e2.name as target_name, e2.entity_type as target_type
        FROM relations r
        JOIN entities e2 ON r.target_id = e2.entity_id AND r.target_type = 'entity'
        WHERE r.source_id = ? AND r.source_type = 'entity'
        ORDER BY r.confidence DESC
    """, (eid,)).fetchall()

    incoming = db.execute("""
        SELECT r.relation_type, r.confidence, e1.name as source_name, e1.entity_type as source_type
        FROM relations r
        JOIN entities e1 ON r.source_id = e1.entity_id AND r.source_type = 'entity'
        WHERE r.target_id = ? AND r.target_type = 'entity'
        ORDER BY r.confidence DESC
    """, (eid,)).fetchall()

    result = {
        "entity": dict(entity),
        "outgoing_relations": [dict(r) for r in outgoing],
        "incoming_relations": [dict(r) for r in incoming]
    }

    # 2-hop if requested
    if hops >= 2:
        hop2 = []
        for r in outgoing:
            target = db.execute(
                "SELECT entity_id FROM entities WHERE name=?", (r["target_name"],)
            ).fetchone()
            if target:
                r2 = db.execute("""
                    SELECT r.relation_type, e2.name as target_name
                    FROM relations r
                    JOIN entities e2 ON r.target_id = e2.entity_id AND r.target_type = 'entity'
                    WHERE r.source_id = ? AND r.source_type = 'entity'
                    LIMIT 5
                """, (target["entity_id"],)).fetchall()
                hop2.extend([dict(x) for x in r2])
        result["hop2_relations"] = hop2

    print(json.dumps(result, indent=2, default=str))

elif COMMAND == "communities":
    # Detect communities via connected components and persist to DB
    print("[graph] Detecting communities (connected components with confidence > 0.7)...")

    components = db.execute("""
        WITH RECURSIVE component AS (
            SELECT DISTINCT source_id as entity_id, source_id as root
            FROM relations WHERE source_type = 'entity' AND confidence > 0.7
            UNION
            SELECT r.target_id, c.root
            FROM relations r
            JOIN component c ON r.source_id = c.entity_id
            WHERE r.target_type = 'entity' AND r.confidence > 0.7
        )
        SELECT root, GROUP_CONCAT(DISTINCT entity_id) as members, COUNT(DISTINCT entity_id) as size
        FROM component
        GROUP BY root
        HAVING size > 2
        ORDER BY size DESC
        LIMIT 30
    """).fetchall()

    # Persist to graph_communities table
    import time
    db.execute("DELETE FROM graph_communities")
    stored = 0
    for comp in components:
        members = comp["members"].split(",")
        # Get entity names for summary
        names = []
        types = set()
        for eid in members:
            e = db.execute("SELECT name, entity_type, ontology_id FROM entities WHERE entity_id=?", (eid,)).fetchone()
            if e:
                names.append(e["name"])
                types.add(e["entity_type"])

        # Build summary from entity names and types
        summary = f"Cluster of {len(members)} entities ({', '.join(sorted(types))}): {', '.join(names[:5])}"
        if len(names) > 5:
            summary += f" +{len(names)-5} more"

        ts = hex(int(time.time() * 1000))[2:]
        import random, string
        rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        community_id = f"{ts}{rand}"

        db.execute(
            "INSERT INTO graph_communities (community_id, entity_ids, summary, paper_count, name) VALUES (?,?,?,?,?)",
            (community_id, json.dumps(members), summary, len(members),
             f"community_{stored+1}_{'-'.join(sorted(types))}")
        )
        stored += 1

    db.commit()
    print(f"[graph] Stored {stored} communities")
    print(json.dumps([dict(c) for c in components], indent=2))

elif COMMAND == "stats":
    entities = db.execute("SELECT entity_type, COUNT(*) as cnt FROM entities GROUP BY entity_type").fetchall()
    relations = db.execute("SELECT relation_type, COUNT(*) as cnt FROM relations GROUP BY relation_type").fetchall()
    print(json.dumps({
        "entities_by_type": {r["entity_type"]: r["cnt"] for r in entities},
        "relations_by_type": {r["relation_type"]: r["cnt"] for r in relations},
        "total_entities": sum(r["cnt"] for r in entities),
        "total_relations": sum(r["cnt"] for r in relations)
    }, indent=2))

db.close()
PYEOF
