#!/usr/bin/env python
"""Phase 10H: Extended limited production-style retrieval A/B (7+7).

Compares current retrieval (ExistingFindingsSource + flat generation)
against graph-native retrieval (HybridKGEvidenceSource + graph-conditioned
generation) with corrected diversity metrics and graph caching.

Changes from Phase 10G:
  - 7 campaigns per arm (up from 6)
  - Segment-level source_ids (diversity fix from Deliverable A)
  - Graph caching active (Deliverable B)
  - Expanded diversity panel: unique_sources, source_type_diversity,
    top_source_concentration, evidence_pack_diversity_score

All other variables held constant:
  - Policy: evidence_diversity_v1
  - Embedding: qwen3-embedding:4b (Regime 2)
  - Generation: qwen3.5:9b-q4_K_M
  - Domain: clean-energy

Arms:
  1. Current: default LadderConfig (ExistingFindingsSource + flat)
  2. Graph-native: LadderConfig with evidence_source_override + enable_graph_context

Outputs to runtime/phase10h/
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("BT_EMBEDDING_MODEL", "qwen3-embedding:4b")
os.environ.setdefault("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")

from breakthrough_engine.db import Repository, init_db  # noqa: E402
from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig  # noqa: E402
from breakthrough_engine.evidence_source import ExistingFindingsSource  # noqa: E402
from breakthrough_engine.hybrid_retrieval import HybridKGEvidenceSource  # noqa: E402
from breakthrough_engine.kg_retrieval import KGEvidenceSource  # noqa: E402
from breakthrough_engine.policy_registry import PolicyRegistry  # noqa: E402

logger = logging.getLogger("phase10h")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

OUTDIR = os.path.join(ROOT, "runtime", "phase10h")
DB_PATH = os.path.join(ROOT, "runtime", "db", "scires.db")
DOMAIN = "clean-energy"
CAMPAIGNS_PER_ARM = 7


# ---------------------------------------------------------------------------
# Campaign result dataclass (expanded diversity panel)
# ---------------------------------------------------------------------------

@dataclass
class CampaignResult:
    campaign_id: str = ""
    arm: str = ""
    campaign_num: int = 0
    status: str = ""
    champion_title: str = ""
    champion_score: float = 0.0
    finalist_count: int = 0
    candidate_count: int = 0
    evidence_items: int = 0
    unique_sources: int = 0
    source_type_diversity: int = 0  # count of distinct source_type values
    top_source_concentration: float = 0.0
    evidence_pack_diversity_score: float = 0.0  # unique_sources / evidence_items
    source_types: dict = field(default_factory=dict)
    run_id: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""
    evidence_source: str = ""
    graph_conditioned: bool = False

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "arm": self.arm,
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
            "run_id": self.run_id,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "error": self.error,
            "evidence_source": self.evidence_source,
            "graph_conditioned": self.graph_conditioned,
        }


# ---------------------------------------------------------------------------
# Run one campaign arm
# ---------------------------------------------------------------------------

def run_campaign_arm(
    arm_name: str,
    repo: Repository,
    config: LadderConfig,
) -> list[CampaignResult]:
    """Run CAMPAIGNS_PER_ARM campaigns for one arm."""
    results = []
    ladder = DailySearchLadder()
    registry = PolicyRegistry(repo)

    for i in range(CAMPAIGNS_PER_ARM):
        print(f"  [{arm_name}] Campaign {i+1}/{CAMPAIGNS_PER_ARM}...", end="", flush=True)
        t0 = time.time()
        result = CampaignResult(
            arm=arm_name,
            campaign_num=i + 1,
            evidence_source=(
                type(config.evidence_source_override).__name__
                if config.evidence_source_override
                else "ExistingFindingsSource"
            ),
            graph_conditioned=config.enable_graph_context,
        )

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
                        result.champion_score = max(
                            result.champion_score, stage.best_score
                        )

            # Get run_id from DB (LadderStageResult has no run_id field)
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

            # Get score from DB if we have run_id
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

                # Expanded diversity panel from evidence packs
                try:
                    pack_rows = repo.db.execute(
                        """SELECT source_diversity_count
                           FROM bt_evidence_packs
                           WHERE candidate_id IN (
                               SELECT id FROM bt_candidates WHERE run_id = ?
                           )""",
                        (result.run_id,),
                    ).fetchall()
                    if pack_rows:
                        div_counts = [
                            (r[0] if isinstance(r, tuple) else r["source_diversity_count"])
                            for r in pack_rows if (r[0] if isinstance(r, tuple) else r["source_diversity_count"])
                        ]
                        if div_counts:
                            result.unique_sources = round(sum(div_counts) / len(div_counts), 1)
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

            print(f" done ({elapsed:.0f}s) — {result.champion_title[:55]}")

        except Exception as e:
            elapsed = time.time() - t0
            result.status = "failed"
            result.error = str(e)[:200]
            result.elapsed_seconds = elapsed
            print(f" FAILED ({elapsed:.0f}s): {str(e)[:80]}")

        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Review label generation
# ---------------------------------------------------------------------------

def generate_review_labels(
    repo: Repository,
    campaigns: list[CampaignResult],
) -> list[dict]:
    """Generate review labels for champions and runner-ups.

    Uses automated scoring signals as proxy:
    - approve if final_score >= 0.85 and plausibility >= 0.7
    - reject if final_score < 0.6 or plausibility < 0.4
    - defer otherwise
    """
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
                "reviewer_note": f"phase10h_auto_{camp.arm}",
                "reviewer": "phase10h_automated",
                "arm": camp.arm,
            }

            repo.save_review_label(label)
            labels.append(label)

    return labels


# ---------------------------------------------------------------------------
# Comparison (expanded diversity panel)
# ---------------------------------------------------------------------------

def compare_arms(
    current_campaigns: list[CampaignResult],
    graph_campaigns: list[CampaignResult],
    labels: list[dict],
) -> dict:
    """Compare the two retrieval arms with expanded diversity panel."""

    def arm_stats(campaigns, arm_labels):
        completed = [c for c in campaigns if c.status != "failed"]
        scores = [c.champion_score for c in completed if c.champion_score > 0]
        approve_count = sum(1 for l in arm_labels if l["decision"] == "approve")
        reject_count = sum(1 for l in arm_labels if l["decision"] == "reject")
        defer_count = sum(1 for l in arm_labels if l["decision"] == "defer")
        total_labels = approve_count + reject_count + defer_count
        decisive = approve_count + reject_count

        return {
            "campaigns_completed": len(completed),
            "campaigns_failed": len(campaigns) - len(completed),
            "mean_champion_score": round(sum(scores) / len(scores), 4) if scores else 0,
            "min_champion_score": round(min(scores), 4) if scores else 0,
            "max_champion_score": round(max(scores), 4) if scores else 0,
            "mean_finalist_count": round(
                sum(c.finalist_count for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_candidate_count": round(
                sum(c.candidate_count for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_evidence_items": round(
                sum(c.evidence_items for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_unique_sources": round(
                sum(c.unique_sources for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_source_type_diversity": round(
                sum(c.source_type_diversity for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_top_concentration": round(
                sum(c.top_source_concentration for c in completed) / len(completed), 3
            ) if completed else 0,
            "mean_diversity_score": round(
                sum(c.evidence_pack_diversity_score for c in completed) / len(completed), 3
            ) if completed else 0,
            "mean_elapsed": round(
                sum(c.elapsed_seconds for c in completed) / len(completed), 1
            ) if completed else 0,
            "approve_count": approve_count,
            "reject_count": reject_count,
            "defer_count": defer_count,
            "total_labels": total_labels,
            "approval_rate": round(approve_count / decisive, 3) if decisive > 0 else 0,
        }

    current_labels = [l for l in labels if l["arm"] == "current"]
    graph_labels = [l for l in labels if l["arm"] == "graph_native"]

    current_stats = arm_stats(current_campaigns, current_labels)
    graph_stats = arm_stats(graph_campaigns, graph_labels)

    score_delta = graph_stats["mean_champion_score"] - current_stats["mean_champion_score"]
    diversity_delta = graph_stats["mean_unique_sources"] - current_stats["mean_unique_sources"]

    threshold_checks = {
        "score_preservation": score_delta >= -0.01,
        "score_above_rollback": score_delta >= -0.05,
        "approval_ge_60pct": graph_stats["approval_rate"] >= 0.60,
        "approval_above_rollback": graph_stats["approval_rate"] >= 0.40,
        "diversity_ge_current": graph_stats["mean_unique_sources"] >= current_stats["mean_unique_sources"],
        "no_systematic_failures": graph_stats["campaigns_failed"] <= 1,
    }

    all_pass = all(threshold_checks.values())
    promotion_checks = all(v for k, v in threshold_checks.items()
                          if k in ("score_preservation", "approval_ge_60pct",
                                   "diversity_ge_current", "no_systematic_failures"))

    if all_pass and promotion_checks:
        recommendation = "promote_graph_native_retrieval"
        reason = "All thresholds pass. Graph-native retrieval meets quality bar for promotion."
    elif threshold_checks["score_above_rollback"] and threshold_checks["approval_above_rollback"]:
        recommendation = "continue_limited_ab"
        reason = "Above rollback thresholds but not all promotion criteria met."
    else:
        recommendation = "keep_current_retrieval"
        reason = "Below rollback thresholds — graph-native retrieval not ready."

    return {
        "phase": "10H",
        "campaigns_per_arm": CAMPAIGNS_PER_ARM,
        "current_arm": current_stats,
        "graph_native_arm": graph_stats,
        "score_delta": round(score_delta, 4),
        "diversity_delta": round(diversity_delta, 1),
        "threshold_checks": threshold_checks,
        "all_checks_pass": all_pass,
        "recommendation": recommendation,
        "reason": reason,
        "diversity_metric_version": "segment_level_v2",
        "graph_caching": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_artifacts(
    current_results: list[CampaignResult],
    graph_results: list[CampaignResult],
    labels: list[dict],
    comparison: dict,
):
    """Export all artifacts to OUTDIR."""
    all_campaigns = current_results + graph_results

    # arm_summary.json
    with open(f"{OUTDIR}/arm_summary.json", "w") as f:
        json.dump([r.to_dict() for r in all_campaigns], f, indent=2)

    # comparison_summary.json
    with open(f"{OUTDIR}/comparison_summary.json", "w") as f:
        json.dump(comparison, f, indent=2)

    # champions.csv
    with open(f"{OUTDIR}/champions.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "campaign_num", "campaign_id", "champion_title",
                     "champion_score", "finalist_count", "unique_sources",
                     "source_type_diversity", "diversity_score",
                     "top_concentration", "evidence_source", "graph_conditioned"])
        for r in all_campaigns:
            if r.status != "failed":
                w.writerow([
                    r.arm, r.campaign_num, r.campaign_id[:16],
                    r.champion_title[:80], round(r.champion_score, 4),
                    r.finalist_count, r.unique_sources,
                    r.source_type_diversity,
                    round(r.evidence_pack_diversity_score, 3),
                    round(r.top_source_concentration, 3),
                    r.evidence_source, r.graph_conditioned,
                ])

    # campaign_metrics.csv
    with open(f"{OUTDIR}/campaign_metrics.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "campaign_num", "campaign_id", "status",
                     "champion_score", "finalist_count", "candidate_count",
                     "evidence_items", "unique_sources", "source_type_diversity",
                     "diversity_score", "top_concentration",
                     "elapsed_seconds", "evidence_source", "graph_conditioned"])
        for r in all_campaigns:
            w.writerow([
                r.arm, r.campaign_num, r.campaign_id[:16], r.status,
                round(r.champion_score, 4), r.finalist_count, r.candidate_count,
                r.evidence_items, r.unique_sources, r.source_type_diversity,
                round(r.evidence_pack_diversity_score, 3),
                round(r.top_source_concentration, 3),
                round(r.elapsed_seconds, 1),
                r.evidence_source, r.graph_conditioned,
            ])

    # review_labels.csv
    with open(f"{OUTDIR}/review_labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arm", "campaign_id", "candidate_role", "decision",
                     "novelty_confidence", "technical_plausibility",
                     "commercialization_relevance", "key_flaw", "candidate_title"])
        for l in labels:
            w.writerow([
                l["arm"], l["campaign_id"][:16], l["candidate_role"],
                l["decision"], l["novelty_confidence"],
                l["technical_plausibility"], l["commercialization_relevance"],
                l["key_flaw"], l["candidate_title"][:80],
            ])

    # label_completion_summary.json
    label_summary = {
        "total_labels": len(labels),
        "by_arm": {
            "current": sum(1 for l in labels if l["arm"] == "current"),
            "graph_native": sum(1 for l in labels if l["arm"] == "graph_native"),
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
        "completeness": "all_campaigns_labeled" if len(labels) >= len(
            [r for r in all_campaigns if r.status != "failed"]
        ) else "incomplete",
    }
    with open(f"{OUTDIR}/label_completion_summary.json", "w") as f:
        json.dump(label_summary, f, indent=2)

    # Markdown comparison summary
    ca = comparison["current_arm"]
    ga = comparison["graph_native_arm"]

    lines = [
        "# Phase 10H: Extended Limited Retrieval A/B — Comparison Summary",
        "",
        f"**Date:** {comparison['timestamp']}",
        f"**Campaigns per arm:** {CAMPAIGNS_PER_ARM}",
        f"**Policy:** evidence_diversity_v1 (fixed)",
        f"**Embedding:** qwen3-embedding:4b (Regime 2)",
        f"**Generation:** qwen3.5:9b-q4_K_M",
        f"**Diversity metric:** segment_level_v2 (corrected)",
        f"**Graph caching:** enabled",
        "",
        "## Arm Comparison",
        "",
        "| Metric | Current | Graph Native | Delta |",
        "|--------|---------|-------------|-------|",
        f"| Campaigns completed | {ca['campaigns_completed']} | {ga['campaigns_completed']} | |",
        f"| Mean champion score | {ca['mean_champion_score']} | {ga['mean_champion_score']} | {comparison['score_delta']:+.4f} |",
        f"| Min champion score | {ca['min_champion_score']} | {ga['min_champion_score']} | |",
        f"| Max champion score | {ca['max_champion_score']} | {ga['max_champion_score']} | |",
        f"| Approval rate | {ca['approval_rate']:.1%} | {ga['approval_rate']:.1%} | |",
        f"| Mean finalists | {ca['mean_finalist_count']} | {ga['mean_finalist_count']} | |",
        f"| Mean evidence items | {ca['mean_evidence_items']} | {ga['mean_evidence_items']} | |",
        f"| Mean unique sources | {ca['mean_unique_sources']} | {ga['mean_unique_sources']} | {comparison['diversity_delta']:+.1f} |",
        f"| Mean source type diversity | {ca['mean_source_type_diversity']} | {ga['mean_source_type_diversity']} | |",
        f"| Mean diversity score | {ca['mean_diversity_score']:.3f} | {ga['mean_diversity_score']:.3f} | |",
        f"| Mean top concentration | {ca['mean_top_concentration']:.1%} | {ga['mean_top_concentration']:.1%} | |",
        f"| Mean elapsed (s) | {ca['mean_elapsed']} | {ga['mean_elapsed']} | |",
        "",
        "## Threshold Checks",
        "",
        "| Check | Result |",
        "|-------|--------|",
    ]
    for k, v in comparison["threshold_checks"].items():
        lines.append(f"| {k} | {'PASS' if v else 'FAIL'} |")

    lines += [
        "",
        f"## Recommendation: `{comparison['recommendation']}`",
        "",
        f"**Reason:** {comparison['reason']}",
        "",
        "## Review Labels",
        "",
        f"- Total: {label_summary['total_labels']}",
        f"- Current arm: {label_summary['by_arm']['current']}",
        f"- Graph native arm: {label_summary['by_arm']['graph_native']}",
        f"- Approve: {label_summary['by_decision']['approve']}",
        f"- Defer: {label_summary['by_decision']['defer']}",
        f"- Reject: {label_summary['by_decision']['reject']}",
        f"- Completeness: {label_summary['completeness']}",
        "",
        "## Current Arm Campaigns",
        "",
        "| # | Score | Finalists | Sources | Type Div | Div Score | Concentration | Champion |",
        "|---|-------|-----------|---------|----------|-----------|---------------|---------|",
    ]
    for r in current_results:
        if r.status != "failed":
            lines.append(
                f"| {r.campaign_num} | {r.champion_score:.4f} | {r.finalist_count} | "
                f"{r.unique_sources} | {r.source_type_diversity} | "
                f"{r.evidence_pack_diversity_score:.3f} | "
                f"{r.top_source_concentration:.1%} | "
                f"{r.champion_title[:45]} |"
            )
    lines += [
        "",
        "## Graph Native Arm Campaigns",
        "",
        "| # | Score | Finalists | Sources | Type Div | Div Score | Concentration | Champion |",
        "|---|-------|-----------|---------|----------|-----------|---------------|---------|",
    ]
    for r in graph_results:
        if r.status != "failed":
            lines.append(
                f"| {r.campaign_num} | {r.champion_score:.4f} | {r.finalist_count} | "
                f"{r.unique_sources} | {r.source_type_diversity} | "
                f"{r.evidence_pack_diversity_score:.3f} | "
                f"{r.top_source_concentration:.1%} | "
                f"{r.champion_title[:45]} |"
            )

    with open(f"{OUTDIR}/comparison_summary.md", "w") as f:
        f.write("\n".join(lines) + "\n")

    # label_completion_summary.md
    with open(f"{OUTDIR}/label_completion_summary.md", "w") as f:
        f.write("# Phase 10H: Label Completion Summary\n\n")
        f.write(f"**Total labels:** {label_summary['total_labels']}\n")
        f.write(f"**Completeness:** {label_summary['completeness']}\n\n")
        f.write("| Metric | Count |\n|--------|-------|\n")
        f.write(f"| Current arm labels | {label_summary['by_arm']['current']} |\n")
        f.write(f"| Graph native arm labels | {label_summary['by_arm']['graph_native']} |\n")
        f.write(f"| Champions labeled | {label_summary['by_role']['champion']} |\n")
        f.write(f"| Runner-ups labeled | {label_summary['by_role']['runner_up']} |\n")
        f.write(f"| Approve | {label_summary['by_decision']['approve']} |\n")
        f.write(f"| Defer | {label_summary['by_decision']['defer']} |\n")
        f.write(f"| Reject | {label_summary['by_decision']['reject']} |\n")


# ---------------------------------------------------------------------------
# Comparability report
# ---------------------------------------------------------------------------

def write_comparability_report():
    """Write comparability lock artifact."""
    report = {
        "phase": "10H",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "comparability_ok": True,
        "held_constant": {
            "policy": "evidence_diversity_v1",
            "embedding_model": "qwen3-embedding:4b",
            "embedding_regime": "regime_2",
            "generation_model": "qwen3.5:9b-q4_K_M",
            "domain": "clean-energy",
            "labeling_schema": "approve/reject/defer + novelty/plausibility/relevance",
            "candidate_budget": "7 per stage (default)",
        },
        "experimental_variable": "retrieval_path",
        "control_arm": {
            "evidence_source": "ExistingFindingsSource",
            "generation_template": "EVIDENCE_BLOCK_TEMPLATE (flat)",
            "graph_context": False,
        },
        "graph_arm": {
            "evidence_source": "HybridKGEvidenceSource",
            "generation_template": "GRAPH_CONDITIONED_TEMPLATE",
            "graph_context": True,
        },
        "changes_from_phase10g": {
            "diversity_metric": "segment_level_v2 (was paper_level_v1)",
            "graph_caching": "enabled (new)",
            "campaigns_per_arm": "7 (was 6)",
        },
        "production_default_unchanged": True,
    }
    with open(f"{OUTDIR}/comparability_report.json", "w") as f:
        json.dump(report, f, indent=2)
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t_start = time.time()

    print("=" * 60)
    print("Phase 10H: Extended Limited Retrieval A/B (7+7)")
    print("CORRECTED DIVERSITY METRICS + GRAPH CACHING")
    print("Policy: evidence_diversity_v1 | Embedding: qwen3-embedding:4b")
    print("=" * 60)

    os.makedirs(OUTDIR, exist_ok=True)

    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    # Check campaign lock
    lock_path = os.path.join(ROOT, "runtime", "campaign.lock")
    if os.path.exists(lock_path):
        print(f"WARNING: campaign.lock exists at {lock_path}")
        print("Remove it if stale (from killed run), or wait for active campaign to finish.")
        sys.exit(1)

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    repo = Repository(db)

    # Write comparability report (Deliverable C)
    comp_report = write_comparability_report()
    print(f"\nComparability report: {json.dumps(comp_report['held_constant'], indent=2)}")
    print(f"Changes from 10G: {json.dumps(comp_report['changes_from_phase10g'], indent=2)}")

    # ARM 1: Current production retrieval
    print(f"\n[ARM 1] Current production retrieval ({CAMPAIGNS_PER_ARM} campaigns)...")
    current_config = LadderConfig(mode="benchmark")
    current_results = run_campaign_arm("current", repo, current_config)

    # ARM 2: Graph-native hybrid retrieval
    print(f"\n  Building graph-native evidence source...")
    trusted_source = ExistingFindingsSource(db)
    kg_source = KGEvidenceSource(repo)
    hybrid_source = HybridKGEvidenceSource(
        trusted_source=trusted_source,
        kg_source=kg_source,
        min_trusted_quota=12,
        kg_diversification_quota=8,
    )
    print(f"  HybridKGEvidenceSource ready")

    print(f"\n[ARM 2] Graph-native hybrid retrieval ({CAMPAIGNS_PER_ARM} campaigns)...")
    graph_config = LadderConfig(
        mode="benchmark",
        evidence_source_override=hybrid_source,
        enable_graph_context=True,
    )
    graph_results = run_campaign_arm("graph_native", repo, graph_config)

    # Check abort conditions
    graph_completed = [r for r in graph_results if r.status != "failed"]
    if len(graph_results) > 0 and len(graph_completed) < len(graph_results) * 0.5:
        print("\nWARNING: >50% graph-native campaigns failed — experiment may need abort review")

    # Collect review labels (Deliverable E)
    print("\n--- Collecting review labels ---")
    all_campaigns = current_results + graph_results
    labels = generate_review_labels(repo, all_campaigns)
    print(f"Generated {len(labels)} review labels")

    # Compare arms (Deliverable F)
    print("\n--- Comparing arms ---")
    comparison = compare_arms(current_results, graph_results, labels)

    # Export all artifacts (Deliverable J)
    print("\n--- Exporting artifacts ---")
    export_artifacts(current_results, graph_results, labels, comparison)

    elapsed_total = round(time.time() - t_start, 1)

    # Print summary
    ca = comparison["current_arm"]
    ga = comparison["graph_native_arm"]
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")
    print(f"\nCurrent arm: {ca['campaigns_completed']} campaigns completed")
    print(f"  Mean score:      {ca['mean_champion_score']}")
    print(f"  Approval:        {ca['approval_rate']:.1%}")
    print(f"  Unique sources:  {ca['mean_unique_sources']}")
    print(f"  Type diversity:  {ca['mean_source_type_diversity']}")
    print(f"  Diversity score: {ca['mean_diversity_score']:.3f}")
    print(f"  Concentration:   {ca['mean_top_concentration']:.1%}")
    print(f"\nGraph-native arm: {ga['campaigns_completed']} campaigns completed")
    print(f"  Mean score:      {ga['mean_champion_score']}")
    print(f"  Approval:        {ga['approval_rate']:.1%}")
    print(f"  Unique sources:  {ga['mean_unique_sources']}")
    print(f"  Type diversity:  {ga['mean_source_type_diversity']}")
    print(f"  Diversity score: {ga['mean_diversity_score']:.3f}")
    print(f"  Concentration:   {ga['mean_top_concentration']:.1%}")
    print(f"\nScore delta: {comparison['score_delta']:+.4f}")
    print(f"Diversity delta: {comparison['diversity_delta']:+.1f}")
    print(f"\nThreshold checks:")
    for k, v in comparison["threshold_checks"].items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"\nAll checks pass: {comparison['all_checks_pass']}")
    print(f"RECOMMENDATION: {comparison['recommendation']}")
    print(f"Reason: {comparison['reason']}")
    print(f"\nTotal elapsed: {elapsed_total}s")
    print(f"Artifacts: {OUTDIR}")
    print(f"{'=' * 60}")

    db.close()


if __name__ == "__main__":
    main()
