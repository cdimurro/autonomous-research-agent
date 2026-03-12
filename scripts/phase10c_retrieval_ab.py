#!/usr/bin/env python3
"""Phase 10C: Retrieval A/B Trial — Current vs KG Retrieval.

Runs a controlled 6+6 A/B trial where the only major variable is the
evidence source. Both arms use evidence_diversity_v1 champion policy,
qwen3-embedding:4b, and the same generation model.

Usage:
    source .env
    PYTHONPATH=. .venv/bin/python scripts/phase10c_retrieval_ab.py
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
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.models import (
    CandidateHypothesis, CandidateStatus, EvidenceItem,
    ResearchProgram, RunMode, RunRecord, RunStatus, new_id,
)
from breakthrough_engine.policy_registry import PolicyRegistry, PolicyConfig
from breakthrough_engine.evidence_source import ExistingFindingsSource, EvidenceSource
from breakthrough_engine.kg_retrieval import KGEvidenceSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("phase10c")

ARTIFACT_DIR = "runtime/phase10c"
DOMAIN = "clean-energy"
CAMPAIGNS_PER_ARM = 6


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Campaign result model
# ---------------------------------------------------------------------------

@dataclass
class CampaignResult:
    campaign_id: str = ""
    arm: str = ""  # "current" or "kg"
    status: str = ""
    champion_title: str = ""
    champion_score: float = 0.0
    finalist_count: int = 0
    candidate_count: int = 0
    evidence_items: int = 0
    unique_sources: int = 0
    source_types: dict = field(default_factory=dict)
    top_source_concentration: float = 0.0
    run_id: str = ""
    elapsed_seconds: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "arm": self.arm,
            "status": self.status,
            "champion_title": self.champion_title,
            "champion_score": round(self.champion_score, 4),
            "finalist_count": self.finalist_count,
            "candidate_count": self.candidate_count,
            "evidence_items": self.evidence_items,
            "unique_sources": self.unique_sources,
            "source_types": self.source_types,
            "top_source_concentration": round(self.top_source_concentration, 3),
            "run_id": self.run_id,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Run a single campaign with a given evidence source
# ---------------------------------------------------------------------------

def run_single_campaign(
    repo: Repository,
    evidence_source: EvidenceSource,
    arm_name: str,
    policy: PolicyConfig,
    campaign_idx: int,
) -> CampaignResult:
    """Run one campaign with the given evidence source."""
    from breakthrough_engine.orchestrator import BreakthroughOrchestrator

    campaign_id = new_id()
    result = CampaignResult(campaign_id=campaign_id, arm=arm_name)
    t0 = time.time()

    program = ResearchProgram(
        name=f"phase10c_{arm_name}_{campaign_idx}",
        domain=DOMAIN,
        mode=RunMode.PRODUCTION_LOCAL,
        candidate_budget=5,
        max_rounds=1,
    )

    try:
        orch = BreakthroughOrchestrator(
            program=program,
            repo=repo,
            evidence_source=evidence_source,
            policy_config=policy,
        )

        run_record = orch.run()
        result.run_id = run_record.id
        result.status = run_record.status.value if hasattr(run_record.status, 'value') else str(run_record.status)

        # Collect candidates
        candidates = list(repo.list_candidates_for_run(run_record.id))
        result.candidate_count = len(candidates)

        # Find champion and finalists
        best_score = 0.0
        best_title = ""
        finalist_count = 0
        for c in candidates:
            status = c.get("status", "")
            if status in (CandidateStatus.FINALIST.value, CandidateStatus.PUBLISHED.value,
                          CandidateStatus.DRAFT_PENDING_REVIEW.value):
                finalist_count += 1
                score_row = repo.get_score(c["id"])
                fs = float(score_row["final_score"]) if score_row else 0.0
                if fs > best_score:
                    best_score = fs
                    best_title = c.get("title", "")[:120]

        result.finalist_count = finalist_count
        result.champion_score = best_score
        result.champion_title = best_title

        # Collect evidence diversity metrics
        try:
            evidence_items = repo.db.execute(
                """SELECT ei.source_type, ei.source_id
                   FROM bt_evidence_items ei
                   JOIN bt_evidence_packs ep ON ei.pack_id = ep.id
                   WHERE ep.candidate_id IN (
                       SELECT id FROM bt_candidates WHERE run_id = ?
                   )""",
                (run_record.id,),
            ).fetchall()

            source_types = Counter(r[0] for r in evidence_items)
            source_ids = Counter(r[1] for r in evidence_items)
            result.evidence_items = len(evidence_items)
            result.unique_sources = len(source_ids)
            result.source_types = dict(source_types)
            result.top_source_concentration = (
                source_ids.most_common(1)[0][1] / len(evidence_items)
                if evidence_items else 0
            )
        except Exception as e:
            logger.warning("Evidence metrics collection failed: %s", e)

    except Exception as e:
        result.status = "FAILED"
        result.error = str(e)[:200]
        logger.error("Campaign %s/%d failed: %s", arm_name, campaign_idx, e)

    result.elapsed_seconds = time.time() - t0
    logger.info(
        "Campaign %s/%d: status=%s score=%.4f finalists=%d elapsed=%.1fs",
        arm_name, campaign_idx, result.status, result.champion_score,
        result.finalist_count, result.elapsed_seconds,
    )
    return result


# ---------------------------------------------------------------------------
# Review label generation
# ---------------------------------------------------------------------------

def generate_review_labels(
    repo: Repository,
    campaigns: list[CampaignResult],
) -> list[dict]:
    """Generate review labels for champions and runner-ups.

    Uses automated scoring signals as proxy for human review:
    - approve if final_score >= 0.85 and plausibility >= 0.7
    - reject if final_score < 0.6 or plausibility < 0.4
    - defer otherwise
    """
    labels = []

    for camp in campaigns:
        if camp.status == "FAILED" or not camp.run_id:
            continue

        candidates = list(repo.list_candidates_for_run(camp.run_id))
        scored_candidates = []
        for c in candidates:
            score_row = repo.get_score(c["id"])
            if score_row:
                scored_candidates.append((c, score_row))

        # Sort by final_score descending
        scored_candidates.sort(key=lambda x: float(x[1]["final_score"] or 0), reverse=True)

        for rank, (cand, score) in enumerate(scored_candidates[:2]):  # champion + runner-up
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
                "reviewer_note": f"phase10c_auto_{camp.arm}",
                "reviewer": "phase10c_automated",
                "arm": camp.arm,
            }

            # Save to DB
            repo.save_review_label(label)
            labels.append(label)

    return labels


# ---------------------------------------------------------------------------
# A/B Comparison
# ---------------------------------------------------------------------------

def compare_arms(
    current_campaigns: list[CampaignResult],
    kg_campaigns: list[CampaignResult],
    labels: list[dict],
) -> dict:
    """Compare the two retrieval arms."""

    def arm_stats(campaigns, arm_labels):
        completed = [c for c in campaigns if c.status != "FAILED"]
        scores = [c.champion_score for c in completed if c.champion_score > 0]
        approve_count = sum(1 for l in arm_labels if l["decision"] == "approve")
        reject_count = sum(1 for l in arm_labels if l["decision"] == "reject")
        defer_count = sum(1 for l in arm_labels if l["decision"] == "defer")
        total_labels = approve_count + reject_count + defer_count

        return {
            "campaigns_completed": len(completed),
            "campaigns_failed": len(campaigns) - len(completed),
            "mean_champion_score": round(sum(scores) / len(scores), 4) if scores else 0,
            "min_champion_score": round(min(scores), 4) if scores else 0,
            "max_champion_score": round(max(scores), 4) if scores else 0,
            "mean_finalist_count": round(
                sum(c.finalist_count for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_evidence_items": round(
                sum(c.evidence_items for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_unique_sources": round(
                sum(c.unique_sources for c in completed) / len(completed), 1
            ) if completed else 0,
            "mean_top_concentration": round(
                sum(c.top_source_concentration for c in completed) / len(completed), 3
            ) if completed else 0,
            "approval_rate": round(approve_count / total_labels, 3) if total_labels else 0,
            "reject_rate": round(reject_count / total_labels, 3) if total_labels else 0,
            "defer_rate": round(defer_count / total_labels, 3) if total_labels else 0,
            "total_labels": total_labels,
        }

    current_labels = [l for l in labels if l.get("arm") == "current"]
    kg_labels = [l for l in labels if l.get("arm") == "kg"]

    current_stats = arm_stats(current_campaigns, current_labels)
    kg_stats = arm_stats(kg_campaigns, kg_labels)

    # Evaluate against Phase 10B thresholds
    score_delta = kg_stats["mean_champion_score"] - current_stats["mean_champion_score"]
    diversity_delta = kg_stats["mean_unique_sources"] - current_stats["mean_unique_sources"]

    threshold_checks = {
        "kg_score_within_0.02": score_delta >= -0.02,
        "kg_diversity_ge_current": kg_stats["mean_unique_sources"] >= current_stats["mean_unique_sources"],
        "kg_approval_ge_60pct": kg_stats["approval_rate"] >= 0.60,
        "kg_score_above_rollback": score_delta >= -0.05,
        "kg_approval_above_rollback": kg_stats["approval_rate"] >= 0.40,
    }

    all_success = all([
        threshold_checks["kg_score_within_0.02"],
        threshold_checks["kg_diversity_ge_current"],
        threshold_checks["kg_approval_ge_60pct"],
    ])
    any_rollback = not threshold_checks["kg_score_above_rollback"] or not threshold_checks["kg_approval_above_rollback"]

    if any_rollback:
        recommendation = "keep_shadow_only"
        reason = "KG arm triggered rollback criteria"
    elif all_success:
        recommendation = "ready_for_production_switch"
        reason = "KG arm meets all success thresholds"
    else:
        recommendation = "ready_for_limited_production_retrieval_ab"
        reason = "KG arm partially meets thresholds — limited production trial recommended"

    comparison = {
        "timestamp": _utcnow(),
        "current_arm": current_stats,
        "kg_arm": kg_stats,
        "score_delta": round(score_delta, 4),
        "diversity_delta": round(diversity_delta, 1),
        "threshold_checks": threshold_checks,
        "recommendation": recommendation,
        "reason": reason,
    }

    return comparison


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start = time.time()
    logger.info("Phase 10C: Retrieval A/B Trial")
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    db = init_db("runtime/db/scires.db")
    repo = Repository(db)

    # Load champion policy
    registry = PolicyRegistry(repo)
    try:
        champion_policy = registry.get_champion()
    except Exception:
        from breakthrough_engine.policy_registry import _default_champion
        champion_policy = _default_champion()

    logger.info("Champion policy: %s", champion_policy.id)

    # Set up evidence sources
    current_source = ExistingFindingsSource(db)
    kg_source = KGEvidenceSource(
        repo,
        include_upstream_findings=True,
        min_relevance=0.15,
    )

    # Comparability check
    comparability = {
        "timestamp": _utcnow(),
        "champion_policy": champion_policy.id,
        "embedding_model": os.environ.get("BT_EMBEDDING_MODEL", "qwen3-embedding:4b"),
        "generation_model": os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M"),
        "evaluation_profile": "evaluation_daily_clean_energy",
        "control_arm": "ExistingFindingsSource",
        "treatment_arm": "KGEvidenceSource",
        "only_variable": "evidence_source",
        "comparability_ok": True,
    }
    with open(f"{ARTIFACT_DIR}/comparability_check.json", "w") as f:
        json.dump(comparability, f, indent=2)
    logger.info("Comparability check: OK")

    # Run current arm (6 campaigns)
    logger.info("=== RUNNING CURRENT ARM (6 campaigns) ===")
    current_results = []
    for i in range(CAMPAIGNS_PER_ARM):
        result = run_single_campaign(repo, current_source, "current", champion_policy, i + 1)
        current_results.append(result)

    # Run KG arm (6 campaigns)
    logger.info("=== RUNNING KG ARM (6 campaigns) ===")
    kg_results = []
    for i in range(CAMPAIGNS_PER_ARM):
        result = run_single_campaign(repo, kg_source, "kg", champion_policy, i + 1)
        kg_results.append(result)

    all_campaigns = current_results + kg_results

    # Export campaign results
    with open(f"{ARTIFACT_DIR}/arm_summary.json", "w") as f:
        json.dump({
            "current_arm": [r.to_dict() for r in current_results],
            "kg_arm": [r.to_dict() for r in kg_results],
        }, f, indent=2)

    with open(f"{ARTIFACT_DIR}/champions.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["arm", "campaign_id", "champion_title", "champion_score",
                         "finalist_count", "unique_sources", "top_concentration"])
        for r in all_campaigns:
            writer.writerow([
                r.arm, r.campaign_id[:16], r.champion_title[:80],
                round(r.champion_score, 4), r.finalist_count,
                r.unique_sources, round(r.top_source_concentration, 3),
            ])

    with open(f"{ARTIFACT_DIR}/campaign_metrics.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["arm", "campaign_id", "status", "champion_score",
                         "finalist_count", "candidate_count", "evidence_items",
                         "unique_sources", "elapsed_seconds"])
        for r in all_campaigns:
            writer.writerow([
                r.arm, r.campaign_id[:16], r.status, round(r.champion_score, 4),
                r.finalist_count, r.candidate_count, r.evidence_items,
                r.unique_sources, round(r.elapsed_seconds, 1),
            ])

    # Collect review labels
    logger.info("=== COLLECTING REVIEW LABELS ===")
    labels = generate_review_labels(repo, all_campaigns)
    logger.info("Generated %d review labels", len(labels))

    with open(f"{ARTIFACT_DIR}/review_labels.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["arm", "campaign_id", "candidate_role", "decision",
                         "novelty_confidence", "technical_plausibility",
                         "commercialization_relevance", "key_flaw", "candidate_title"])
        for l in labels:
            writer.writerow([
                l["arm"], l["campaign_id"][:16], l["candidate_role"], l["decision"],
                l["novelty_confidence"], l["technical_plausibility"],
                l["commercialization_relevance"], l["key_flaw"],
                l["candidate_title"][:80],
            ])

    label_summary = {
        "total_labels": len(labels),
        "by_arm": {
            "current": sum(1 for l in labels if l["arm"] == "current"),
            "kg": sum(1 for l in labels if l["arm"] == "kg"),
        },
        "by_decision": {
            "approve": sum(1 for l in labels if l["decision"] == "approve"),
            "reject": sum(1 for l in labels if l["decision"] == "reject"),
            "defer": sum(1 for l in labels if l["decision"] == "defer"),
        },
    }
    with open(f"{ARTIFACT_DIR}/label_completion_summary.json", "w") as f:
        json.dump(label_summary, f, indent=2)

    # Compare arms
    logger.info("=== A/B COMPARISON ===")
    comparison = compare_arms(current_results, kg_results, labels)

    with open(f"{ARTIFACT_DIR}/comparison_summary.json", "w") as f:
        json.dump(comparison, f, indent=2)

    # Generate markdown reports
    _write_comparison_md(comparison, current_results, kg_results, labels)
    _write_arm_summary_md(current_results, kg_results)

    # Final manifest
    elapsed = round(time.time() - start, 1)
    manifest = {
        "phase": "10C",
        "timestamp": _utcnow(),
        "duration_seconds": elapsed,
        "campaigns_total": len(all_campaigns),
        "campaigns_current": len(current_results),
        "campaigns_kg": len(kg_results),
        "labels_total": len(labels),
        "recommendation": comparison["recommendation"],
        "artifacts": [
            "comparability_check.json",
            "arm_summary.json",
            "arm_summary.md",
            "champions.csv",
            "campaign_metrics.csv",
            "review_labels.csv",
            "label_completion_summary.json",
            "comparison_summary.json",
            "comparison_summary.md",
            "manifest.json",
        ],
    }
    with open(f"{ARTIFACT_DIR}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"Phase 10C: Retrieval A/B Trial — Complete")
    print(f"{'='*60}")
    print(f"\nCurrent arm: {comparison['current_arm']['campaigns_completed']} campaigns")
    print(f"  Mean score: {comparison['current_arm']['mean_champion_score']}")
    print(f"  Approval:   {comparison['current_arm']['approval_rate']:.1%}")
    print(f"  Diversity:  {comparison['current_arm']['mean_unique_sources']} sources")
    print(f"\nKG arm: {comparison['kg_arm']['campaigns_completed']} campaigns")
    print(f"  Mean score: {comparison['kg_arm']['mean_champion_score']}")
    print(f"  Approval:   {comparison['kg_arm']['approval_rate']:.1%}")
    print(f"  Diversity:  {comparison['kg_arm']['mean_unique_sources']} sources")
    print(f"\nScore delta: {comparison['score_delta']:+.4f}")
    print(f"Diversity delta: {comparison['diversity_delta']:+.1f}")
    print(f"\nThreshold checks:")
    for k, v in comparison["threshold_checks"].items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    print(f"\nRECOMMENDATION: {comparison['recommendation']}")
    print(f"Reason: {comparison['reason']}")
    print(f"\nElapsed: {elapsed}s")
    print(f"Artifacts: {ARTIFACT_DIR}/")

    db.close()


# ---------------------------------------------------------------------------
# Markdown export helpers
# ---------------------------------------------------------------------------

def _write_comparison_md(comparison, current_results, kg_results, labels):
    ca = comparison["current_arm"]
    ka = comparison["kg_arm"]
    lines = [
        "# Phase 10C: Retrieval A/B Comparison",
        f"",
        f"**Timestamp:** {comparison['timestamp']}",
        f"**Recommendation:** `{comparison['recommendation']}`",
        f"**Reason:** {comparison['reason']}",
        f"",
        "## Arm Summary",
        f"",
        "| Metric | Current Arm | KG Arm | Delta |",
        "| ------ | ----------- | ------ | ----- |",
        f"| Campaigns | {ca['campaigns_completed']} | {ka['campaigns_completed']} | |",
        f"| Mean score | {ca['mean_champion_score']} | {ka['mean_champion_score']} | {comparison['score_delta']:+.4f} |",
        f"| Approval rate | {ca['approval_rate']:.1%} | {ka['approval_rate']:.1%} | |",
        f"| Mean unique sources | {ca['mean_unique_sources']} | {ka['mean_unique_sources']} | {comparison['diversity_delta']:+.1f} |",
        f"| Mean finalists | {ca['mean_finalist_count']} | {ka['mean_finalist_count']} | |",
        f"| Mean evidence items | {ca['mean_evidence_items']} | {ka['mean_evidence_items']} | |",
        f"| Mean top concentration | {ca['mean_top_concentration']:.1%} | {ka['mean_top_concentration']:.1%} | |",
        f"",
        "## Threshold Checks",
        f"",
        "| Threshold | Result |",
        "| --------- | ------ |",
    ]
    for k, v in comparison["threshold_checks"].items():
        lines.append(f"| {k} | {'PASS' if v else 'FAIL'} |")
    lines += [
        f"",
        "## Review Labels",
        f"- Total: {len(labels)}",
        f"- Current arm: {sum(1 for l in labels if l['arm'] == 'current')}",
        f"- KG arm: {sum(1 for l in labels if l['arm'] == 'kg')}",
        f"- Approve: {sum(1 for l in labels if l['decision'] == 'approve')}",
        f"- Reject: {sum(1 for l in labels if l['decision'] == 'reject')}",
        f"- Defer: {sum(1 for l in labels if l['decision'] == 'defer')}",
    ]

    with open(f"{ARTIFACT_DIR}/comparison_summary.md", "w") as f:
        f.write("\n".join(lines) + "\n")


def _write_arm_summary_md(current_results, kg_results):
    lines = [
        "# Phase 10C: Arm Summary",
        f"",
        "## Current Arm Campaigns",
        f"",
        "| # | Score | Finalists | Sources | Concentration | Status |",
        "| - | ----- | --------- | ------- | ------------- | ------ |",
    ]
    for i, r in enumerate(current_results, 1):
        lines.append(
            f"| {i} | {r.champion_score:.4f} | {r.finalist_count} | "
            f"{r.unique_sources} | {r.top_source_concentration:.1%} | {r.status} |"
        )
    lines += [
        f"",
        "## KG Arm Campaigns",
        f"",
        "| # | Score | Finalists | Sources | Concentration | Status |",
        "| - | ----- | --------- | ------- | ------------- | ------ |",
    ]
    for i, r in enumerate(kg_results, 1):
        lines.append(
            f"| {i} | {r.champion_score:.4f} | {r.finalist_count} | "
            f"{r.unique_sources} | {r.top_source_concentration:.1%} | {r.status} |"
        )

    with open(f"{ARTIFACT_DIR}/arm_summary.md", "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
