#!/usr/bin/env python
"""Phase 10F: Bounded downstream campaign comparison with REAL graph wiring.

Unlike Phase 10E-Prime's campaign comparison (which ran both arms identically),
this script uses LadderConfig.evidence_source_override and
LadderConfig.enable_graph_context to inject the graph-native path
into the actual orchestrator pipeline.

Arms:
  1. Current: Standard ExistingFindingsSource + flat generation
  2. Graph-native: HybridKGEvidenceSource + graph-conditioned generation

Outputs to runtime/phase10f/campaign_comparison/
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

os.environ.setdefault("BT_EMBEDDING_MODEL", "qwen3-embedding:4b")
os.environ.setdefault("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
from breakthrough_engine.evidence_source import ExistingFindingsSource
from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource
from breakthrough_engine.kg_calibration import EvidenceCalibrator
from breakthrough_engine.kg_retrieval import KGEvidenceSource
from breakthrough_engine.policy_registry import PolicyRegistry

OUTDIR = os.path.join(ROOT, "runtime", "phase10f", "campaign_comparison")
DB_PATH = os.path.join(ROOT, "runtime", "db", "scires.db")
DOMAIN = "clean-energy"
CAMPAIGNS_PER_ARM = 3


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def run_campaign_arm(
    arm_name: str,
    repo: Repository,
    db: sqlite3.Connection,
    config: LadderConfig,
) -> list[dict]:
    """Run campaigns for one arm using the specified LadderConfig."""
    results = []
    ladder = DailySearchLadder()
    registry = PolicyRegistry(repo)

    for i in range(CAMPAIGNS_PER_ARM):
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
                "evidence_source": type(config.evidence_source_override).__name__ if config.evidence_source_override else "ExistingFindingsSource",
                "graph_conditioned": config.enable_graph_context,
            }
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
    print("Phase 10F: Downstream Campaign Comparison (3+3)")
    print("REAL GRAPH WIRING — evidence source + generation template")
    print("=" * 60)

    ensure_dir(OUTDIR)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    repo = Repository(db)

    # ARM 1: Current production retrieval (default LadderConfig)
    print("\n[ARM 1] Current production retrieval (ExistingFindingsSource + flat)...")
    current_config = LadderConfig(mode="benchmark")
    current_results = run_campaign_arm("current", repo, db, current_config)

    # ARM 2: Graph-native hybrid retrieval with graph-conditioned generation
    print("\n  Building graph-native evidence source...")
    trusted_source = ExistingFindingsSource(db)
    kg_source = KGEvidenceSource(db)
    hybrid_source = HybridKGEvidenceSource(
        trusted_source=trusted_source,
        kg_source=kg_source,
        min_trusted_quota=12,
        kg_diversification_quota=8,
    )
    print(f"  HybridKGEvidenceSource ready (trusted + KG)")

    print("\n[ARM 2] Graph-native hybrid retrieval + graph-conditioned generation...")
    graph_config = LadderConfig(
        mode="benchmark",
        evidence_source_override=hybrid_source,
        enable_graph_context=True,
    )
    graph_results = run_campaign_arm("graph_native", repo, db, graph_config)

    # Combine results
    all_results = current_results + graph_results

    # Export JSON
    with open(os.path.join(OUTDIR, "arm_summary.json"), "w") as f:
        json.dump(all_results, f, indent=2)

    # CSV
    with open(os.path.join(OUTDIR, "campaign_metrics.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "campaign_num", "status", "champion_title", "champion_score",
                     "total_candidates", "total_shortlisted", "elapsed_seconds",
                     "evidence_source", "graph_conditioned"])
        for r in all_results:
            w.writerow([
                r.get("arm"), r.get("campaign_num"), r.get("status"),
                r.get("champion_title", "")[:80], r.get("champion_score", ""),
                r.get("total_candidates", 0), r.get("total_shortlisted", 0),
                r.get("elapsed_seconds", 0),
                r.get("evidence_source", ""), r.get("graph_conditioned", False),
            ])

    # Markdown summary
    with open(os.path.join(OUTDIR, "arm_summary.md"), "w") as f:
        f.write("# Downstream Campaign Comparison — Phase 10F\n\n")
        f.write(f"**Date:** {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"**Arms:** {CAMPAIGNS_PER_ARM} campaigns each\n")
        f.write(f"**Policy:** evidence_diversity_v1 (fixed)\n")
        f.write(f"**REAL WIRING:** Graph arm uses HybridKGEvidenceSource + graph-conditioned generation\n\n")

        for arm in ["current", "graph_native"]:
            arm_data = [r for r in all_results if r.get("arm") == arm]
            completed = [r for r in arm_data if r.get("status") == "completed"]
            f.write(f"## {arm.replace('_', ' ').title()} Arm\n\n")
            if arm == "current":
                f.write("- Evidence: ExistingFindingsSource (default)\n")
                f.write("- Generation: flat template (standard)\n")
            else:
                f.write("- Evidence: **HybridKGEvidenceSource** (trusted + KG)\n")
                f.write("- Generation: **graph-conditioned template** (GRAPH_CONDITIONED_TEMPLATE)\n")
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

    print(f"\n{'=' * 60}")
    print(f"Campaign comparison complete. Artifacts: {OUTDIR}")
    print(f"{'=' * 60}")

    db.close()


if __name__ == "__main__":
    main()
