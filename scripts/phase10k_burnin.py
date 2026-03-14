"""Phase 10K: Graph-native retrieval production burn-in.

Runs 3 evaluation + 3 production campaigns using graph-native retrieval
as the default evidence source (via CampaignManager with the Phase 10K
promotion wiring).

All variables held constant:
  - Policy: evidence_diversity_v1
  - Embedding: qwen3-embedding:4b (Regime 2)
  - Generation: qwen3.5:9b-q4_K_M
  - Domain: clean-energy
  - Graph caching: enabled (Phase 10H)
  - evidence_refs diversity check: enabled (Phase 10J)
  - Source-aware hybrid pool: enabled (Phase 10J)

This script runs campaigns through the standard CampaignManager pipeline,
which now has graph-native retrieval wired as default (Phase 10K).
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from breakthrough_engine.db import Repository, init_db  # noqa: E402
from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig  # noqa: E402
from breakthrough_engine.evidence_source import ExistingFindingsSource  # noqa: E402
from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource  # noqa: E402
from breakthrough_engine.kg_retrieval import KGEvidenceSource  # noqa: E402
from breakthrough_engine.policy_registry import PolicyRegistry  # noqa: E402

logger = logging.getLogger("phase10k")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

OUTDIR = os.path.join(ROOT, "runtime", "phase10k")
DB_PATH = os.path.join(ROOT, "runtime", "db", "scires.db")
DOMAIN = "clean-energy"

# Burn-in: 3 eval + 3 prod = 6 campaigns
EVAL_CAMPAIGNS = 3
PROD_CAMPAIGNS = 3

# Phase 9E baseline for comparison
PRIOR_BASELINE = {
    "baseline_id": "phase9e_promoted_production_regime2",
    "policy": "evidence_diversity_v1",
    "mean_champion_score": 0.9126,
    "approval_rate": 0.833,
    "mean_novelty": 0.853,
    "mean_plausibility": 0.855,
    "mean_unique_sources": 2.0,
}


# ---------------------------------------------------------------------------
# Campaign result dataclass
# ---------------------------------------------------------------------------

@dataclass
class CampaignResult:
    campaign_id: str = ""
    profile: str = ""
    campaign_num: int = 0
    status: str = ""
    champion_title: str = ""
    champion_score: float = 0.0
    finalist_count: int = 0
    candidate_count: int = 0
    evidence_items: int = 0
    unique_sources: int = 0
    source_type_diversity: int = 0
    top_source_concentration: float = 0.0
    evidence_pack_diversity_score: float = 0.0
    source_types: dict = field(default_factory=dict)
    packs_with_items: int = 0
    total_packs: int = 0
    persistence_rate: float = 0.0
    run_id: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "profile": self.profile,
            "campaign_num": self.campaign_num,
            "status": self.status,
            "champion_title": self.champion_title,
            "champion_score": round(self.champion_score, 4),
            "finalist_count": self.finalist_count,
            "candidate_count": self.candidate_count,
            "evidence_items": self.evidence_items,
            "unique_sources": self.unique_sources,
            "source_type_diversity": self.source_type_diversity,
            "top_source_concentration": round(self.top_source_concentration, 3),
            "evidence_pack_diversity_score": round(self.evidence_pack_diversity_score, 3),
            "source_types": self.source_types,
            "packs_with_items": self.packs_with_items,
            "total_packs": self.total_packs,
            "persistence_rate": round(self.persistence_rate, 3),
            "run_id": self.run_id,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Run one campaign
# ---------------------------------------------------------------------------

def run_single_campaign(
    profile: str,
    campaign_num: int,
    repo: Repository,
    config: LadderConfig,
    registry: PolicyRegistry,
) -> CampaignResult:
    """Run a single campaign and collect metrics."""
    ladder = DailySearchLadder()
    result = CampaignResult(profile=profile, campaign_num=campaign_num)

    print(f"  [{profile}] Campaign {campaign_num}...", end="", flush=True)
    t0 = time.time()

    try:
        campaign_result = ladder.run_campaign(
            repo=repo,
            config=config,
            policy_registry=registry,
        )
        elapsed = time.time() - t0
        result.campaign_id = campaign_result.campaign_id
        result.status = "completed"
        result.champion_title = campaign_result.daily_champion_title or ""
        result.elapsed_seconds = elapsed

        # Extract champion score from ladder stages
        if campaign_result.ladder_stages:
            for stage in campaign_result.ladder_stages:
                if hasattr(stage, "best_score") and stage.best_score:
                    result.champion_score = max(result.champion_score, stage.best_score)

        # Get run_id from DB
        try:
            row = repo.db.execute(
                """SELECT c.run_id FROM bt_daily_campaigns dc
                   JOIN bt_candidates c ON c.id = dc.champion_candidate_id
                   WHERE dc.campaign_id = ?""",
                (result.campaign_id,),
            ).fetchone()
            if row:
                result.run_id = row[0] if isinstance(row, tuple) else row["run_id"]
        except Exception:
            pass

        # Get detailed metrics from DB
        if result.run_id:
            candidates = list(repo.list_candidates_for_run(result.run_id))
            result.candidate_count = len(candidates)

            for c in candidates:
                score_row = repo.get_score(c["id"])
                if score_row:
                    fs = float(score_row["final_score"] or 0)
                    if fs > result.champion_score:
                        result.champion_score = fs
                    if fs > 0:
                        result.finalist_count += 1

            # Evidence pack persistence audit
            try:
                pack_rows = repo.db.execute(
                    """SELECT ep.id, ep.source_diversity_count,
                              (SELECT COUNT(*) FROM bt_evidence_items ei WHERE ei.pack_id = ep.id) as item_count
                       FROM bt_evidence_packs ep
                       WHERE ep.candidate_id IN (
                           SELECT id FROM bt_candidates WHERE run_id = ?
                       )""",
                    (result.run_id,),
                ).fetchall()
                if pack_rows:
                    result.total_packs = len(pack_rows)
                    result.packs_with_items = sum(
                        1 for r in pack_rows
                        if (r[2] if isinstance(r, tuple) else r["item_count"]) > 0
                    )
                    result.persistence_rate = (
                        result.packs_with_items / result.total_packs
                        if result.total_packs > 0 else 0.0
                    )
            except Exception:
                pass

            # Evidence item details
            try:
                evidence_rows = repo.db.execute(
                    """SELECT ei.source_type, ei.source_id
                       FROM bt_evidence_items ei
                       JOIN bt_evidence_packs ep ON ei.pack_id = ep.id
                       WHERE ep.candidate_id IN (
                           SELECT id FROM bt_candidates WHERE run_id = ?
                       )""",
                    (result.run_id,),
                ).fetchall()
                if evidence_rows:
                    source_types = Counter(r[0] if isinstance(r, tuple) else r["source_type"] for r in evidence_rows)
                    source_ids = Counter(r[1] if isinstance(r, tuple) else r["source_id"] for r in evidence_rows)
                    result.evidence_items = len(evidence_rows)
                    result.unique_sources = len(source_ids)
                    result.source_type_diversity = len(source_types)
                    result.source_types = dict(source_types)
                    result.top_source_concentration = (
                        max(source_ids.values()) / len(evidence_rows)
                        if evidence_rows else 0.0
                    )
                    result.evidence_pack_diversity_score = (
                        len(source_ids) / len(evidence_rows)
                        if evidence_rows else 0.0
                    )
            except Exception:
                pass

        result.candidate_count = max(
            result.candidate_count,
            campaign_result.total_candidates_generated or 0,
        )

        print(f" done ({elapsed:.0f}s) packs={result.packs_with_items}/{result.total_packs}"
              f" sources={result.unique_sources} — {result.champion_title[:50]}")

    except Exception as e:
        elapsed = time.time() - t0
        result.status = "failed"
        result.error = str(e)[:200]
        result.elapsed_seconds = elapsed
        print(f" FAILED ({elapsed:.0f}s): {str(e)[:80]}")

    return result


# ---------------------------------------------------------------------------
# Review label generation
# ---------------------------------------------------------------------------

def generate_review_labels(repo: Repository, campaigns: list[CampaignResult]) -> list[dict]:
    """Generate review labels for champions and one runner-up per campaign."""
    labels = []

    for camp in campaigns:
        if camp.status == "failed" or not camp.run_id:
            continue

        candidates = list(repo.list_candidates_for_run(camp.run_id))
        scored_candidates = []
        for c in candidates:
            score_row = repo.get_score(c["id"])
            if score_row:
                scored_candidates.append((c, score_row))

        scored_candidates.sort(
            key=lambda x: float(x[1]["final_score"] or 0), reverse=True
        )

        for rank, (cand, score) in enumerate(scored_candidates[:2]):
            fs = float(score["final_score"] or 0)
            plaus = float(score.get("plausibility_score") or 0.5)
            novelty = float(score.get("novelty_score") or 0.5)
            evidence = float(score.get("evidence_strength_score") or 0.5)

            if fs >= 0.85 and plaus >= 0.7:
                decision = "approve"
            elif fs < 0.6 or plaus < 0.4:
                decision = "reject"
            else:
                decision = "defer"

            label = {
                "campaign_id": camp.campaign_id,
                "candidate_id": cand["id"],
                "candidate_title": cand.get("title", "")[:200],
                "candidate_role": "champion" if rank == 0 else "runner_up",
                "decision": decision,
                "novelty_confidence": round(min(1.0, novelty), 3),
                "technical_plausibility": round(min(1.0, plaus), 3),
                "commercialization_relevance": round(min(1.0, evidence * 0.8), 3),
                "key_flaw": "" if decision == "approve" else (
                    "low_plausibility" if plaus < 0.4 else
                    "low_overall_score" if fs < 0.6 else
                    "borderline_quality"
                ),
                "reviewer_note": f"phase10k_burnin_{camp.profile}",
                "reviewer": "phase10k_automated",
                "profile": camp.profile,
            }

            repo.save_review_label(label)
            labels.append(label)

    return labels


# ---------------------------------------------------------------------------
# Burn-in summary and comparison against prior baseline
# ---------------------------------------------------------------------------

def compute_burnin_summary(
    results: list[CampaignResult],
    labels: list[dict],
) -> dict:
    """Compute burn-in summary and compare against prior baseline."""
    completed = [c for c in results if c.status != "failed"]
    scores = [c.champion_score for c in completed if c.champion_score > 0]

    approve_count = sum(1 for l in labels if l["decision"] == "approve")
    reject_count = sum(1 for l in labels if l["decision"] == "reject")
    defer_count = sum(1 for l in labels if l["decision"] == "defer")
    decisive = approve_count + reject_count
    total_labels = approve_count + reject_count + defer_count

    eval_results = [c for c in completed if c.profile == "evaluation"]
    prod_results = [c for c in completed if c.profile == "production"]

    burnin = {
        "phase": "10K",
        "type": "burnin",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_campaigns": len(results),
        "completed": len(completed),
        "failed": len(results) - len(completed),
        "eval_campaigns": len(eval_results),
        "prod_campaigns": len(prod_results),
        "mean_champion_score": round(sum(scores) / len(scores), 4) if scores else 0,
        "min_champion_score": round(min(scores), 4) if scores else 0,
        "max_champion_score": round(max(scores), 4) if scores else 0,
        "mean_finalist_count": round(
            sum(c.finalist_count for c in completed) / len(completed), 1
        ) if completed else 0,
        "mean_unique_sources": round(
            sum(c.unique_sources for c in completed) / len(completed), 1
        ) if completed else 0,
        "mean_diversity_score": round(
            sum(c.evidence_pack_diversity_score for c in completed) / len(completed), 3
        ) if completed else 0,
        "mean_top_concentration": round(
            sum(c.top_source_concentration for c in completed) / len(completed), 3
        ) if completed else 0,
        "mean_persistence_rate": round(
            sum(c.persistence_rate for c in completed) / len(completed), 3
        ) if completed else 0,
        "mean_elapsed": round(
            sum(c.elapsed_seconds for c in completed) / len(completed), 1
        ) if completed else 0,
        "approve_count": approve_count,
        "reject_count": reject_count,
        "defer_count": defer_count,
        "total_labels": total_labels,
        "approval_rate": round(approve_count / decisive, 3) if decisive > 0 else 0,
        "retrieval_source": "HybridKGEvidenceSource",
        "graph_context": True,
        "policy": "evidence_diversity_v1",
        "embedding": "qwen3-embedding:4b",
        "generation": "qwen3.5:9b-q4_K_M",
    }

    # Compare against prior baseline
    prior = PRIOR_BASELINE
    score_delta = burnin["mean_champion_score"] - prior["mean_champion_score"]
    approval_delta = burnin["approval_rate"] - prior["approval_rate"]
    diversity_delta = burnin["mean_unique_sources"] - prior["mean_unique_sources"]

    comparison = {
        "prior_baseline": prior,
        "burnin_metrics": burnin,
        "score_delta": round(score_delta, 4),
        "approval_delta": round(approval_delta, 3),
        "diversity_delta": round(diversity_delta, 1),
        "health_checks": {
            "score_preserved": score_delta >= -0.01,
            "score_above_rollback": score_delta >= -0.05,
            "approval_ge_60pct": burnin["approval_rate"] >= 0.60,
            "approval_above_rollback": burnin["approval_rate"] >= 0.40,
            "no_systematic_failures": burnin["failed"] <= 1,
            "persistence_ok": burnin["mean_persistence_rate"] >= 0.90,
        },
    }

    all_healthy = all(comparison["health_checks"].values())
    comparison["all_healthy"] = all_healthy

    if all_healthy:
        comparison["recommendation"] = "ready_to_merge_and_adopt"
        comparison["reason"] = "Burn-in healthy across all checks. Graph-native retrieval holds up in production-like use."
    elif comparison["health_checks"]["score_above_rollback"] and comparison["health_checks"]["approval_above_rollback"]:
        comparison["recommendation"] = "keep_rollout_branch_only"
        comparison["reason"] = "Above rollback thresholds but not all health checks pass."
    else:
        comparison["recommendation"] = "rollback_to_current_retrieval"
        comparison["reason"] = "Below rollback thresholds. Revert to prior retrieval."

    return comparison


# ---------------------------------------------------------------------------
# Export artifacts
# ---------------------------------------------------------------------------

def export_artifacts(
    results: list[CampaignResult],
    labels: list[dict],
    comparison: dict,
):
    """Export all artifacts to OUTDIR."""
    # burnin_summary.json
    with open(f"{OUTDIR}/burnin_summary.json", "w") as f:
        json.dump(comparison, f, indent=2)

    # campaign_metrics.csv
    with open(f"{OUTDIR}/campaign_metrics.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile", "campaign_num", "campaign_id", "status", "champion_title",
                     "champion_score", "finalist_count", "unique_sources",
                     "diversity_score", "top_concentration", "packs_with_items",
                     "total_packs", "persistence_rate", "elapsed_seconds"])
        for r in results:
            w.writerow([
                r.profile, r.campaign_num, r.campaign_id[:16], r.status,
                r.champion_title[:60], round(r.champion_score, 4),
                r.finalist_count, r.unique_sources,
                round(r.evidence_pack_diversity_score, 3),
                round(r.top_source_concentration, 3),
                r.packs_with_items, r.total_packs,
                round(r.persistence_rate, 3), round(r.elapsed_seconds, 1),
            ])

    # champions.csv
    with open(f"{OUTDIR}/champions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile", "campaign_num", "campaign_id", "champion_title",
                     "champion_score", "finalist_count", "unique_sources",
                     "persistence_rate"])
        for r in results:
            if r.status != "failed":
                w.writerow([
                    r.profile, r.campaign_num, r.campaign_id[:16],
                    r.champion_title[:60], round(r.champion_score, 4),
                    r.finalist_count, r.unique_sources,
                    round(r.persistence_rate, 3),
                ])

    # review_labels.csv
    with open(f"{OUTDIR}/review_labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["campaign_id", "candidate_id", "candidate_title", "candidate_role",
                     "decision", "novelty_confidence", "technical_plausibility",
                     "commercialization_relevance", "key_flaw", "reviewer_note", "profile"])
        for l in labels:
            w.writerow([
                l["campaign_id"][:16], l["candidate_id"][:16],
                l["candidate_title"][:60], l["candidate_role"],
                l["decision"], l["novelty_confidence"],
                l["technical_plausibility"], l["commercialization_relevance"],
                l["key_flaw"], l["reviewer_note"], l.get("profile", ""),
            ])

    # label_completion_summary.json
    label_summary = {
        "total_labels": len(labels),
        "by_profile": {
            "evaluation": sum(1 for l in labels if l.get("profile") == "evaluation"),
            "production": sum(1 for l in labels if l.get("profile") == "production"),
        },
        "by_decision": {
            "approve": sum(1 for l in labels if l["decision"] == "approve"),
            "defer": sum(1 for l in labels if l["decision"] == "defer"),
            "reject": sum(1 for l in labels if l["decision"] == "reject"),
        },
        "by_role": {
            "champion": sum(1 for l in labels if l["candidate_role"] == "champion"),
            "runner_up": sum(1 for l in labels if l["candidate_role"] == "runner_up"),
        },
        "completeness": "all_campaigns_labeled" if len(labels) >= len([r for r in results if r.status != "failed"]) else "partial",
    }
    with open(f"{OUTDIR}/label_completion_summary.json", "w") as f:
        json.dump(label_summary, f, indent=2)

    # label_completion_summary.md
    with open(f"{OUTDIR}/label_completion_summary.md", "w") as f:
        f.write("# Phase 10K Burn-in — Label Completion Summary\n\n")
        f.write(f"- Total labels: {label_summary['total_labels']}\n")
        f.write(f"- Evaluation: {label_summary['by_profile']['evaluation']}\n")
        f.write(f"- Production: {label_summary['by_profile']['production']}\n")
        f.write(f"- Approve: {label_summary['by_decision']['approve']}\n")
        f.write(f"- Defer: {label_summary['by_decision']['defer']}\n")
        f.write(f"- Reject: {label_summary['by_decision']['reject']}\n")
        f.write(f"- Champions: {label_summary['by_role']['champion']}\n")
        f.write(f"- Runner-ups: {label_summary['by_role']['runner_up']}\n")
        f.write(f"- Completeness: {label_summary['completeness']}\n")

    # burnin_summary.md
    bm = comparison["burnin_metrics"]
    prior = comparison["prior_baseline"]
    with open(f"{OUTDIR}/burnin_summary.md", "w") as f:
        f.write("# Phase 10K: Graph-Native Retrieval Burn-in Summary\n\n")
        f.write(f"**Date:** {bm['timestamp']}\n")
        f.write(f"**Campaigns:** {bm['total_campaigns']} ({bm['eval_campaigns']} eval + {bm['prod_campaigns']} prod)\n")
        f.write(f"**Retrieval:** {bm['retrieval_source']}\n")
        f.write(f"**Policy:** {bm['policy']}\n\n")
        f.write("## Burn-in vs Prior Baseline\n\n")
        f.write("| Metric | Prior Baseline | Burn-in | Delta |\n")
        f.write("|--------|---------------|---------|-------|\n")
        f.write(f"| Mean champion score | {prior['mean_champion_score']} | {bm['mean_champion_score']} | {comparison['score_delta']:+.4f} |\n")
        f.write(f"| Approval rate | {prior['approval_rate']:.1%} | {bm['approval_rate']:.1%} | {comparison['approval_delta']:+.3f} |\n")
        f.write(f"| Mean unique sources | {prior['mean_unique_sources']} | {bm['mean_unique_sources']} | {comparison['diversity_delta']:+.1f} |\n")
        f.write(f"| Persistence rate | — | {bm['mean_persistence_rate']:.1%} | — |\n")
        f.write(f"| Mean elapsed (s) | — | {bm['mean_elapsed']} | — |\n\n")
        f.write("## Health Checks\n\n")
        f.write("| Check | Result |\n")
        f.write("|-------|--------|\n")
        for k, v in comparison["health_checks"].items():
            f.write(f"| {k} | {'PASS' if v else 'FAIL'} |\n")
        f.write(f"\n## Recommendation: `{comparison['recommendation']}`\n\n")
        f.write(f"**Reason:** {comparison['reason']}\n")

    # finalists_combined.csv (all scored candidates)
    with open(f"{OUTDIR}/finalists_combined.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile", "campaign_num", "campaign_id", "candidate_title", "final_score"])
        # We'll populate this from DB in main()

    print(f"\nArtifacts exported to {OUTDIR}/")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUTDIR, exist_ok=True)

    print("=" * 60)
    print("Phase 10K: Graph-Native Retrieval Production Burn-in")
    print("GRAPH-NATIVE RETRIEVAL AS DEFAULT (Phase 10K promotion)")
    print(f"Policy: evidence_diversity_v1 | Embedding: qwen3-embedding:4b")
    print("=" * 60)

    # Init DB and repo
    db = init_db(DB_PATH)
    repo = Repository(db)
    registry = PolicyRegistry(repo)

    # Build graph-native evidence source (same as campaign_manager.py promotion)
    trusted_source = ExistingFindingsSource(db)
    kg_source = KGEvidenceSource(repo)
    hybrid_source = HybridKGEvidenceSource(
        trusted_source=trusted_source,
        kg_source=kg_source,
        min_trusted_quota=12,
        kg_diversification_quota=8,
        min_kg_items=2,
        max_per_paper=3,
    )
    print(f"  HybridKGEvidenceSource ready")

    all_results = []

    # --- Evaluation campaigns ---
    print(f"\n[EVAL] Running {EVAL_CAMPAIGNS} evaluation campaigns...")
    eval_config = LadderConfig(
        mode="benchmark",
        evidence_source_override=hybrid_source,
        enable_graph_context=True,
    )
    for i in range(EVAL_CAMPAIGNS):
        result = run_single_campaign("evaluation", i + 1, repo, eval_config, registry)
        all_results.append(result)

    # --- Production campaigns ---
    print(f"\n[PROD] Running {PROD_CAMPAIGNS} production campaigns...")
    prod_config = LadderConfig(
        mode="production",
        evidence_source_override=hybrid_source,
        enable_graph_context=True,
    )
    for i in range(PROD_CAMPAIGNS):
        result = run_single_campaign("production", i + 1, repo, prod_config, registry)
        all_results.append(result)

    # --- Review labels ---
    print(f"\n--- Collecting review labels ---")
    labels = generate_review_labels(repo, all_results)
    print(f"Generated {len(labels)} review labels")

    # --- Burn-in comparison ---
    print(f"\n--- Computing burn-in summary ---")
    comparison = compute_burnin_summary(all_results, labels)

    # --- Export finalists_combined.csv with actual data ---
    # We need to do this after campaigns complete
    finalists_data = []
    for r in all_results:
        if r.status == "failed" or not r.run_id:
            continue
        candidates = list(repo.list_candidates_for_run(r.run_id))
        for c in candidates:
            score_row = repo.get_score(c["id"])
            if score_row:
                fs = float(score_row["final_score"] or 0)
                if fs > 0:
                    finalists_data.append({
                        "profile": r.profile,
                        "campaign_num": r.campaign_num,
                        "campaign_id": r.campaign_id[:16],
                        "candidate_title": c.get("title", "")[:60],
                        "final_score": round(fs, 4),
                    })

    # --- Export artifacts ---
    print(f"\n--- Exporting artifacts ---")
    export_artifacts(all_results, labels, comparison)

    # Overwrite finalists_combined.csv with actual data
    with open(f"{OUTDIR}/finalists_combined.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile", "campaign_num", "campaign_id", "candidate_title", "final_score"])
        for fd in finalists_data:
            w.writerow([fd["profile"], fd["campaign_num"], fd["campaign_id"],
                        fd["candidate_title"], fd["final_score"]])

    # --- Print results ---
    bm = comparison["burnin_metrics"]
    prior = comparison["prior_baseline"]

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print()
    print(f"Burn-in: {bm['completed']} campaigns completed ({bm['eval_campaigns']} eval + {bm['prod_campaigns']} prod)")
    print(f"  Mean score:        {bm['mean_champion_score']}")
    print(f"  Approval:          {bm['approval_rate']:.1%}")
    print(f"  Unique sources:    {bm['mean_unique_sources']}")
    print(f"  Diversity score:   {bm['mean_diversity_score']}")
    print(f"  Concentration:     {bm['mean_top_concentration']:.1%}")
    print(f"  Persistence rate:  {bm['mean_persistence_rate']:.1%}")
    print(f"  Mean elapsed:      {bm['mean_elapsed']:.0f}s")
    print()
    print(f"Prior baseline ({prior['baseline_id']}):")
    print(f"  Mean score:        {prior['mean_champion_score']}")
    print(f"  Approval:          {prior['approval_rate']:.1%}")
    print(f"  Unique sources:    {prior['mean_unique_sources']}")
    print()
    print(f"Score delta: {comparison['score_delta']:+.4f}")
    print(f"Approval delta: {comparison['approval_delta']:+.3f}")
    print(f"Diversity delta: {comparison['diversity_delta']:+.1f}")
    print()
    print("Health checks:")
    for k, v in comparison["health_checks"].items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print()
    print(f"All healthy: {comparison['all_healthy']}")
    print(f"RECOMMENDATION: {comparison['recommendation']}")
    print(f"Reason: {comparison['reason']}")
    print()
    elapsed_total = sum(r.elapsed_seconds for r in all_results)
    print(f"Total elapsed: {elapsed_total:.1f}s")
    print(f"Artifacts: {OUTDIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
