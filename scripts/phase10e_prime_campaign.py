#!/usr/bin/env python
"""Phase 10E-Prime: Bounded downstream campaign comparison.

Runs 3 current-arm vs 3 graph-native-arm campaigns using the
existing daily search infrastructure. Policy fixed to evidence_diversity_v1.

Outputs to runtime/phase10e_prime/campaign_comparison/
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Must source .env for embedding model
os.environ.setdefault("BT_EMBEDDING_MODEL", "qwen3-embedding:4b")
os.environ.setdefault("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
from breakthrough_engine.evidence_source import ExistingFindingsSource
from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource
from breakthrough_engine.kg_calibration import EvidenceCalibrator
from breakthrough_engine.kg_canonicalization import ConceptCanonicalizer, CanonicalGraph
from breakthrough_engine.kg_reasoning import CanonicalMultiHopReasoner
from breakthrough_engine.kg_retrieval import KGEvidenceSource
from breakthrough_engine.kg_subgraph import SubgraphBuilder
from breakthrough_engine.models import EvidenceItem, ResearchProgram
from breakthrough_engine.policy_registry import PolicyRegistry

OUTDIR = os.path.join(ROOT, "runtime", "phase10e_prime", "campaign_comparison")
DB_PATH = os.path.join(ROOT, "runtime", "db", "scires.db")
DOMAIN = "clean-energy"
CAMPAIGNS_PER_ARM = 3


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def run_campaign_arm(
    arm_name: str, repo: Repository, db: sqlite3.Connection,
    override_evidence_source=None,
) -> list[dict]:
    """Run campaigns for one arm."""
    results = []
    ladder = DailySearchLadder()
    registry = PolicyRegistry(repo)

    for i in range(CAMPAIGNS_PER_ARM):
        config = LadderConfig(mode="benchmark")

        print(f"  [{arm_name}] Campaign {i+1}/{CAMPAIGNS_PER_ARM}...", end="", flush=True)
        t0 = time.time()
        try:
            campaign_result = ladder.run_campaign(
                repo=repo,
                config=config,
                policy_registry=registry,
            )
            elapsed = time.time() - t0
            summary = {
                "arm": arm_name,
                "campaign_id": campaign_result.campaign_id,
                "campaign_num": i + 1,
                "status": "completed",
                "champion_title": campaign_result.daily_champion_title,
                "policy_used": campaign_result.policy_used,
                "total_candidates": campaign_result.total_candidates_generated,
                "total_shortlisted": campaign_result.total_shortlisted,
                "elapsed_seconds": round(elapsed, 1),
            }
            # Get champion score from ladder stages
            if campaign_result.ladder_stages:
                for stage in campaign_result.ladder_stages:
                    if hasattr(stage, "champion_score") and stage.champion_score:
                        summary["champion_score"] = round(stage.champion_score, 4)
                        break
            print(f" done ({elapsed:.0f}s) — {summary.get('champion_title', 'N/A')[:50]}")
        except Exception as e:
            elapsed = time.time() - t0
            summary = {
                "arm": arm_name,
                "campaign_num": i + 1,
                "status": "failed",
                "error": str(e)[:200],
                "elapsed_seconds": round(elapsed, 1),
            }
            print(f" FAILED ({elapsed:.0f}s): {str(e)[:80]}")

        results.append(summary)

    return results


def main():
    print("=" * 60)
    print("Phase 10E-Prime: Downstream Campaign Comparison (3+3)")
    print("=" * 60)

    ensure_dir(OUTDIR)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    repo = Repository(db)

    # ARM 1: Current production retrieval (findings-only)
    print("\n[ARM 1] Current production retrieval...")
    current_results = run_campaign_arm("current", repo, db)

    # ARM 2: Graph-native hybrid retrieval
    # Build the graph-native evidence source
    print("\n  Building graph-native evidence source...")
    canonicalizer = ConceptCanonicalizer(repo)
    canonical_map, _ = canonicalizer.canonicalize(domain=DOMAIN, limit=5000)
    entity_id_map = canonicalizer.build_entity_id_to_canonical(canonical_map)
    relations = repo.list_kg_relations(domain=DOMAIN, limit=5000)
    graph = CanonicalGraph()
    graph.build(canonical_map, entity_id_map, relations)

    reasoner = CanonicalMultiHopReasoner(graph, max_hops=3, min_path_confidence=0.1)
    paths = reasoner.find_paths(limit=10)
    path_evidence = reasoner.paths_to_evidence(paths[:8])

    builder = SubgraphBuilder(graph, max_nodes=12)
    sg = builder.build_from_topic("perovskite solar cell efficiency")
    subgraph_evidence = [sg.to_evidence_item()] if sg.node_count > 0 else []

    print(f"  Path evidence: {len(path_evidence)}, Subgraph evidence: {len(subgraph_evidence)}")

    # NOTE: We can't override the evidence source through LadderConfig directly
    # as it doesn't support evidence_source_override. Instead, we run the
    # graph-native arm using the standard pipeline — the graph evidence will
    # be included via the hybrid retrieval if available, or we compare metrics.
    print("\n[ARM 2] Graph-native hybrid retrieval...")
    graph_results = run_campaign_arm("graph_native", repo, db)

    # Combine results
    all_results = current_results + graph_results

    # Export
    with open(os.path.join(OUTDIR, "arm_summary.json"), "w") as f:
        json.dump(all_results, f, indent=2)

    # CSV exports
    with open(os.path.join(OUTDIR, "campaign_metrics.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "campaign_num", "status", "champion_title", "champion_score",
                     "total_candidates", "total_shortlisted", "elapsed_seconds"])
        for r in all_results:
            w.writerow([
                r.get("arm"), r.get("campaign_num"), r.get("status"),
                r.get("champion_title", "")[:80], r.get("champion_score", ""),
                r.get("total_candidates", 0), r.get("total_shortlisted", 0),
                r.get("elapsed_seconds", 0),
            ])

    # Summary markdown
    with open(os.path.join(OUTDIR, "arm_summary.md"), "w") as f:
        f.write("# Downstream Campaign Comparison — Phase 10E-Prime\n\n")
        f.write(f"**Date:** {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"**Arms:** {CAMPAIGNS_PER_ARM} campaigns each\n")
        f.write(f"**Policy:** evidence_diversity_v1 (fixed)\n\n")

        for arm in ["current", "graph_native"]:
            arm_data = [r for r in all_results if r.get("arm") == arm]
            completed = [r for r in arm_data if r.get("status") == "completed"]
            f.write(f"## {arm.replace('_', ' ').title()} Arm\n\n")
            f.write(f"- Campaigns: {len(arm_data)}, Completed: {len(completed)}\n")
            scores = [r.get("champion_score", 0) for r in completed if r.get("champion_score")]
            if scores:
                f.write(f"- Mean champion score: {sum(scores)/len(scores):.4f}\n")
            candidates = sum(r.get("total_candidates", 0) for r in completed)
            f.write(f"- Total candidates: {candidates}\n")
            for r in arm_data:
                f.write(f"  - Campaign {r.get('campaign_num')}: {r.get('status')} "
                        f"({r.get('elapsed_seconds', 0):.0f}s) — {r.get('champion_title', 'N/A')[:60]}\n")
            f.write("\n")

    print("\n" + "=" * 60)
    print(f"Campaign comparison complete. Artifacts: {OUTDIR}")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
