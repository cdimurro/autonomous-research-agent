"""Bounded challenger-vs-champion trial runner for the Breakthrough Engine Phase 8B.

Runs a small comparison batch split between the current champion and a single
challenger policy. Produces comparison metrics, promotion readiness assessment,
and exportable artifacts.

Key design decisions:
- Bounded: max 6 campaigns per trial, min 2 per policy arm
- No automatic promotion: produces a recommendation only
- Campaign attribution: each campaign is tagged with policy_id
- Labels required per campaign for full review-signal comparison
- Offline-safe for testing (uses MockCampaignRunner hook)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Promotion assessment outcomes
PROMOTION_RECOMMENDED = "promotion_recommended"
PROMOTION_NOT_RECOMMENDED = "promotion_not_recommended"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"

# Minimum campaigns per arm to draw conclusions
MIN_CAMPAIGNS_PER_ARM = 2


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PolicyArmResult:
    """Results for one policy arm (champion or challenger) in a trial."""
    policy_id: str
    policy_name: str
    campaign_ids: list = field(default_factory=list)
    champion_scores: list = field(default_factory=list)
    finalist_counts: list = field(default_factory=list)
    block_rates: list = field(default_factory=list)
    integrity_ok_count: int = 0
    falsification_complete_count: int = 0
    review_labels_collected: int = 0
    approve_count: int = 0
    reject_count: int = 0
    defer_count: int = 0

    @property
    def campaign_count(self) -> int:
        return len(self.campaign_ids)

    @property
    def mean_champion_score(self) -> Optional[float]:
        if not self.champion_scores:
            return None
        return sum(self.champion_scores) / len(self.champion_scores)

    @property
    def mean_block_rate(self) -> Optional[float]:
        if not self.block_rates:
            return None
        return sum(self.block_rates) / len(self.block_rates)

    @property
    def integrity_ok_rate(self) -> Optional[float]:
        if not self.campaign_ids:
            return None
        return self.integrity_ok_count / len(self.campaign_ids)

    @property
    def falsification_complete_rate(self) -> Optional[float]:
        if not self.campaign_ids:
            return None
        return self.falsification_complete_count / len(self.campaign_ids)

    @property
    def approval_rate(self) -> Optional[float]:
        total = self.approve_count + self.reject_count + self.defer_count
        if total == 0:
            return None
        # Only count approve + reject for binary approval rate (defer abstains)
        decisive = self.approve_count + self.reject_count
        if decisive == 0:
            return None
        return self.approve_count / decisive

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "campaign_count": self.campaign_count,
            "campaign_ids": self.campaign_ids,
            "mean_champion_score": round(self.mean_champion_score, 5) if self.mean_champion_score is not None else None,
            "mean_block_rate": round(self.mean_block_rate, 4) if self.mean_block_rate is not None else None,
            "integrity_ok_rate": round(self.integrity_ok_rate, 3) if self.integrity_ok_rate is not None else None,
            "falsification_complete_rate": round(self.falsification_complete_rate, 3) if self.falsification_complete_rate is not None else None,
            "review_labels_collected": self.review_labels_collected,
            "approve_count": self.approve_count,
            "reject_count": self.reject_count,
            "defer_count": self.defer_count,
            "approval_rate": round(self.approval_rate, 3) if self.approval_rate is not None else None,
            "champion_scores": [round(s, 5) for s in self.champion_scores],
        }


@dataclass
class ChallengerTrialComparison:
    """Comparison between champion and challenger arms."""
    champion_score_delta: Optional[float] = None    # challenger - champion (positive = better)
    block_rate_delta: Optional[float] = None        # challenger - champion (negative = better)
    integrity_ok_rate_delta: Optional[float] = None
    approval_rate_delta: Optional[float] = None
    promotion_assessment: str = INSUFFICIENT_EVIDENCE
    promotion_notes: list = field(default_factory=list)
    evidence_sufficient: bool = False

    def to_dict(self) -> dict:
        return {
            "champion_score_delta": round(self.champion_score_delta, 5) if self.champion_score_delta is not None else None,
            "block_rate_delta": round(self.block_rate_delta, 4) if self.block_rate_delta is not None else None,
            "integrity_ok_rate_delta": round(self.integrity_ok_rate_delta, 3) if self.integrity_ok_rate_delta is not None else None,
            "approval_rate_delta": round(self.approval_rate_delta, 3) if self.approval_rate_delta is not None else None,
            "promotion_assessment": self.promotion_assessment,
            "promotion_notes": self.promotion_notes,
            "evidence_sufficient": self.evidence_sufficient,
        }


@dataclass
class ChallengerTrialResult:
    """Full result of a bounded challenger-vs-champion trial."""
    trial_id: str = ""
    trial_date: str = ""
    champion_arm: Optional[PolicyArmResult] = None
    challenger_arm: Optional[PolicyArmResult] = None
    comparison: Optional[ChallengerTrialComparison] = None
    profile_used: str = ""
    total_campaigns: int = 0
    started_at: str = ""
    completed_at: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "trial_id": self.trial_id,
            "trial_date": self.trial_date,
            "profile_used": self.profile_used,
            "total_campaigns": self.total_campaigns,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
            "champion_arm": self.champion_arm.to_dict() if self.champion_arm else None,
            "challenger_arm": self.challenger_arm.to_dict() if self.challenger_arm else None,
            "comparison": self.comparison.to_dict() if self.comparison else None,
        }


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------

def compare_arms(
    champion: PolicyArmResult,
    challenger: PolicyArmResult,
    baseline_mean_score: Optional[float] = None,
) -> ChallengerTrialComparison:
    """Compare champion and challenger arms and produce a promotion assessment.

    Args:
        champion: Champion arm results
        challenger: Challenger arm results
        baseline_mean_score: Phase 8 reviewed baseline mean score (regression guard)

    Returns:
        ChallengerTrialComparison with promotion_assessment
    """
    notes = []
    comparison = ChallengerTrialComparison()

    # Evidence sufficiency check
    if champion.campaign_count < MIN_CAMPAIGNS_PER_ARM:
        notes.append(f"Insufficient champion campaigns: {champion.campaign_count} < {MIN_CAMPAIGNS_PER_ARM}")
    if challenger.campaign_count < MIN_CAMPAIGNS_PER_ARM:
        notes.append(f"Insufficient challenger campaigns: {challenger.campaign_count} < {MIN_CAMPAIGNS_PER_ARM}")

    if champion.campaign_count < MIN_CAMPAIGNS_PER_ARM or challenger.campaign_count < MIN_CAMPAIGNS_PER_ARM:
        comparison.promotion_assessment = INSUFFICIENT_EVIDENCE
        comparison.promotion_notes = notes
        return comparison

    comparison.evidence_sufficient = True

    # Score comparison
    champ_score = champion.mean_champion_score
    chal_score = challenger.mean_champion_score
    if champ_score is not None and chal_score is not None:
        comparison.champion_score_delta = chal_score - champ_score
        if comparison.champion_score_delta < -0.03:
            notes.append(
                f"Score regression: challenger mean {chal_score:.4f} < champion {champ_score:.4f} "
                f"(delta={comparison.champion_score_delta:+.4f})"
            )
        elif comparison.champion_score_delta >= 0:
            notes.append(
                f"Score improvement: challenger mean {chal_score:.4f} >= champion {champ_score:.4f} "
                f"(delta={comparison.champion_score_delta:+.4f})"
            )
        else:
            notes.append(
                f"Score within tolerance: challenger mean {chal_score:.4f} vs champion {champ_score:.4f} "
                f"(delta={comparison.champion_score_delta:+.4f}, threshold -0.03)"
            )

    # Block rate comparison (lower is better for challenger)
    champ_block = champion.mean_block_rate
    chal_block = challenger.mean_block_rate
    if champ_block is not None and chal_block is not None:
        comparison.block_rate_delta = chal_block - champ_block
        if comparison.block_rate_delta > 0.10:
            notes.append(
                f"Block rate regression: challenger {chal_block:.1%} > champion {champ_block:.1%} "
                f"(+{comparison.block_rate_delta:.1%})"
            )
        else:
            notes.append(
                f"Block rate OK: challenger {chal_block:.1%} vs champion {champ_block:.1%}"
            )

    # Integrity check
    if challenger.integrity_ok_rate is not None and challenger.integrity_ok_rate < 1.0:
        notes.append(
            f"Integrity failures in challenger arm: "
            f"{challenger.integrity_ok_count}/{challenger.campaign_count} OK"
        )

    # Regression guard vs baseline
    if baseline_mean_score is not None and chal_score is not None:
        if chal_score < baseline_mean_score - 0.05:
            notes.append(
                f"Challenger regresses vs Phase 8 baseline: {chal_score:.4f} < "
                f"{baseline_mean_score:.4f} - 0.05 = {baseline_mean_score - 0.05:.4f}"
            )

    # Approval rate comparison (if available)
    champ_approval = champion.approval_rate
    chal_approval = challenger.approval_rate
    if champ_approval is not None and chal_approval is not None:
        comparison.approval_rate_delta = chal_approval - champ_approval
        if comparison.approval_rate_delta < -0.05:
            notes.append(
                f"Review approval regression: challenger {chal_approval:.1%} < "
                f"champion {champ_approval:.1%} (delta={comparison.approval_rate_delta:+.1%})"
            )
        else:
            notes.append(
                f"Review approval OK: challenger {chal_approval:.1%} vs champion {champ_approval:.1%}"
            )

    # Integrity delta
    if champion.integrity_ok_rate is not None and challenger.integrity_ok_rate is not None:
        comparison.integrity_ok_rate_delta = challenger.integrity_ok_rate - champion.integrity_ok_rate

    # Overall assessment
    failing = [n for n in notes if "regression" in n.lower() or "failure" in n.lower()]
    if failing:
        comparison.promotion_assessment = PROMOTION_NOT_RECOMMENDED
    elif comparison.champion_score_delta is not None and comparison.champion_score_delta >= 0:
        comparison.promotion_assessment = PROMOTION_RECOMMENDED
    else:
        # Within tolerance but not clearly better
        comparison.promotion_assessment = INSUFFICIENT_EVIDENCE
        notes.append(
            "More campaigns needed for confident promotion recommendation "
            "(challenger within tolerance but no clear improvement)"
        )

    comparison.promotion_notes = notes
    return comparison


# ---------------------------------------------------------------------------
# Trial results from existing campaign data
# ---------------------------------------------------------------------------

def build_arm_from_campaign_ids(
    db,
    campaign_ids: list[str],
    policy_id: str,
    policy_name: str,
) -> PolicyArmResult:
    """Build a PolicyArmResult from already-run campaign IDs stored in the DB.

    Used to analyze campaigns that were run as part of a trial batch.
    """
    from .label_completeness import _get_labeled_candidate_ids

    arm = PolicyArmResult(policy_id=policy_id, policy_name=policy_name)

    for campaign_id in campaign_ids:
        arm.campaign_ids.append(campaign_id)

        # Get receipt data; use LIKE to handle full vs short campaign IDs
        try:
            row = db.execute(
                "SELECT * FROM bt_campaign_receipts WHERE campaign_id LIKE ? LIMIT 1",
                (campaign_id + "%",),
            ).fetchone()
            if row:
                d = dict(row)

                # champion_score is not in receipts; look it up from bt_scores
                champion_candidate_id = d.get("champion_candidate_id")
                if champion_candidate_id:
                    score_row = db.execute(
                        "SELECT final_score FROM bt_scores WHERE candidate_id=? LIMIT 1",
                        (champion_candidate_id,),
                    ).fetchone()
                    if score_row and score_row["final_score"]:
                        arm.champion_scores.append(float(score_row["final_score"]))

                # Parse status for integrity/falsification
                status = d.get("status", "")
                if status in ("completed_with_draft", "completed_no_draft"):
                    arm.integrity_ok_count += 1
                    arm.falsification_complete_count += 1

                # Parse block rate from metadata if available
                generated = d.get("total_candidates_generated", 0) or 0
                blocked = d.get("total_blocked", 0) or 0
                if generated > 0:
                    arm.block_rates.append(blocked / generated)
        except Exception as e:
            logger.debug("Could not get receipt for %s: %s", campaign_id, e)

        # Try to get champion score from eval pack (fallback)
        _fill_from_eval_pack(arm, campaign_id)

        # Review labels — use prefix LIKE since labels may be stored with short IDs
        try:
            # Try exact match first, then prefix match
            labeled = _get_labeled_candidate_ids(db, campaign_id)
            if not labeled:
                # Labels stored with short ID prefix
                labeled = _get_labeled_candidate_ids(db, campaign_id[:12])
            for cand_id, decision in labeled.items():
                arm.review_labels_collected += 1
                if decision == "approve":
                    arm.approve_count += 1
                elif decision == "reject":
                    arm.reject_count += 1
                elif decision == "defer":
                    arm.defer_count += 1
        except Exception as e:
            logger.debug("Could not get labels for %s: %s", campaign_id, e)

    return arm


def _fill_from_eval_pack(arm: PolicyArmResult, campaign_id: str) -> None:
    """Fill champion score from eval pack finalists.csv if receipt was incomplete."""
    runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
    csv_path = os.path.join(runtime_root, "evaluation_packs", campaign_id, "finalists.csv")

    if not os.path.exists(csv_path):
        return

    try:
        best_score = 0.0
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    score = float(row.get("final_score", 0) or 0)
                    if score > best_score:
                        best_score = score
                except (TypeError, ValueError):
                    pass

        if best_score > 0:
            # Replace or fill champion score if not already set
            if len(arm.champion_scores) < len(arm.campaign_ids):
                arm.champion_scores.append(best_score)
            elif arm.champion_scores and arm.champion_scores[-1] == 0.0:
                arm.champion_scores[-1] = best_score

        # Try to get block rate from pack metadata
        pack_json = os.path.join(
            runtime_root, "evaluation_packs", campaign_id, "evaluation_pack.json"
        )
        if os.path.exists(pack_json):
            try:
                with open(pack_json) as f:
                    pack = json.load(f)
                generated = pack.get("candidates_generated", 0)
                blocked = pack.get("candidates_blocked", 0)
                if generated > 0 and len(arm.block_rates) < len(arm.campaign_ids):
                    arm.block_rates.append(blocked / generated)
            except Exception:
                pass

    except Exception as e:
        logger.debug("Could not read eval pack for %s: %s", campaign_id, e)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_trial_csv(result: ChallengerTrialResult, output_path: Optional[str] = None) -> str:
    """Export trial results to CSV. Returns CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "arm", "policy_id", "policy_name", "campaign_id",
        "champion_score", "block_rate", "integrity_ok",
        "review_labels", "approve", "reject", "defer",
    ])

    for arm_name, arm in [("champion", result.champion_arm), ("challenger", result.challenger_arm)]:
        if arm is None:
            continue
        for i, cid in enumerate(arm.campaign_ids):
            score = arm.champion_scores[i] if i < len(arm.champion_scores) else None
            block = arm.block_rates[i] if i < len(arm.block_rates) else None
            writer.writerow([
                arm_name,
                arm.policy_id,
                arm.policy_name,
                cid,
                f"{score:.5f}" if score else "",
                f"{block:.4f}" if block else "",
                "yes",  # integrity assumed OK for completed campaigns
                "",     # per-campaign label breakdown not tracked here
                "",
                "",
                "",
            ])

    # Summary rows
    writer.writerow([])
    writer.writerow(["# Summary"])
    for arm_name, arm in [("champion", result.champion_arm), ("challenger", result.challenger_arm)]:
        if arm is None:
            continue
        writer.writerow([
            f"# {arm_name}_mean_score", "", "", "",
            f"{arm.mean_champion_score:.5f}" if arm.mean_champion_score else "",
        ])

    content = output.getvalue()
    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(content)
        logger.info("Exported trial CSV to %s", output_path)
    return content


def export_trial_summary_json(result: ChallengerTrialResult, output_path: Optional[str] = None) -> str:
    """Export trial summary as JSON. Returns JSON string."""
    data = result.to_dict()
    content = json.dumps(data, indent=2)
    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(content)
        logger.info("Exported trial JSON to %s", output_path)
    return content


def export_trial_summary_md(result: ChallengerTrialResult, output_path: Optional[str] = None) -> str:
    """Export trial summary as Markdown. Returns Markdown string."""
    champ = result.champion_arm
    chal = result.challenger_arm
    comp = result.comparison

    lines = [
        f"# Challenger Trial: {result.trial_id}",
        f"",
        f"**Date**: {result.trial_date}",
        f"**Profile**: `{result.profile_used}`",
        f"**Total campaigns**: {result.total_campaigns}",
        f"",
        f"---",
        f"",
        f"## Arms",
        f"",
        f"| Metric | Champion ({champ.policy_name if champ else '?'}) | Challenger ({chal.policy_name if chal else '?'}) |",
        f"|--------|---------|-----------|",
    ]

    def _fmt(val, fmt=".4f"):
        return f"{val:{fmt}}" if val is not None else "N/A"

    if champ and chal:
        lines += [
            f"| Campaigns | {champ.campaign_count} | {chal.campaign_count} |",
            f"| Mean champion score | {_fmt(champ.mean_champion_score)} | {_fmt(chal.mean_champion_score)} |",
            f"| Mean block rate | {_fmt(champ.mean_block_rate, '.1%')} | {_fmt(chal.mean_block_rate, '.1%')} |",
            f"| Integrity OK rate | {_fmt(champ.integrity_ok_rate, '.0%')} | {_fmt(chal.integrity_ok_rate, '.0%')} |",
            f"| Review labels | {champ.review_labels_collected} | {chal.review_labels_collected} |",
            f"| Approval rate | {_fmt(champ.approval_rate, '.1%')} | {_fmt(chal.approval_rate, '.1%')} |",
        ]

    lines += ["", "---", "", "## Comparison"]
    if comp:
        lines += [
            f"",
            f"| Metric | Delta (challenger - champion) | Status |",
            f"|--------|------------------------------|--------|",
        ]
        def _status(delta, thresh_bad, lower_is_better=False):
            if delta is None:
                return "N/A"
            if lower_is_better:
                return "✓ OK" if delta <= thresh_bad else "✗ Worse"
            return "✓ OK" if delta >= -thresh_bad else "✗ Regression"

        lines += [
            f"| Champion score | {_fmt(comp.champion_score_delta, '+.4f')} | {_status(comp.champion_score_delta, 0.03)} |",
            f"| Block rate | {_fmt(comp.block_rate_delta, '+.1%')} | {_status(comp.block_rate_delta, 0.10, lower_is_better=True)} |",
            f"| Approval rate | {_fmt(comp.approval_rate_delta, '+.1%')} | {_status(comp.approval_rate_delta, 0.05)} |",
        ]

        lines += ["", f"**Promotion assessment**: `{comp.promotion_assessment}`", ""]
        lines += ["**Notes**:", ""]
        for note in comp.promotion_notes:
            lines.append(f"- {note}")

    lines += [
        "",
        "---",
        "",
        "## Action Required",
        "",
    ]
    if comp and comp.promotion_assessment == PROMOTION_RECOMMENDED:
        lines += [
            "Promotion to probation is recommended based on current evidence.",
            "**Operator must manually run**: `python -m breakthrough_engine policy promote <challenger_id>`",
            "Promotion is NOT automatic.",
        ]
    elif comp and comp.promotion_assessment == PROMOTION_NOT_RECOMMENDED:
        lines += [
            "Promotion is NOT recommended. Challenger shows regression on one or more metrics.",
            "Review notes above. Consider adjusting challenger config or running more campaigns.",
        ]
    else:
        lines += [
            "Insufficient evidence for confident recommendation.",
            "Run additional campaigns with both arms before deciding.",
        ]

    content = "\n".join(lines)
    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(content)
        logger.info("Exported trial MD to %s", output_path)
    return content


# ---------------------------------------------------------------------------
# Artifact manifest
# ---------------------------------------------------------------------------

def build_artifact_manifest(
    phase8_batch_dir: str,
    phase8b_trial_dir: Optional[str],
    baselines_dir: str,
) -> dict:
    """Build a manifest dict of all important runtime artifacts.

    Returns a dict with artifact categories and their file paths.
    """
    manifest = {
        "generated_at": _utcnow(),
        "baselines": {},
        "evaluation_batches": {},
        "challenger_trials": {},
        "review_labels": {},
    }

    # Baselines
    for name, filename in [
        ("phase5_validated", "phase5_validated_benchmark.json"),
        ("phase7d_reviewed", "phase7d_reviewed_baseline.json"),
        ("phase8_reviewed", "phase8_reviewed_baseline.json"),
    ]:
        path = os.path.join(baselines_dir, filename)
        manifest["baselines"][name] = {
            "path": path,
            "exists": os.path.exists(path),
        }

    # Phase 8 batch
    manifest["evaluation_batches"]["phase8_batch_20260309"] = {
        "dir": phase8_batch_dir,
        "batch_summary_json": os.path.join(phase8_batch_dir, "batch_summary.json"),
        "batch_summary_md": os.path.join(phase8_batch_dir, "batch_summary.md"),
        "label_targets_csv": os.path.join(phase8_batch_dir, "label_targets.csv"),
        "review_labels_csv": os.path.join(phase8_batch_dir, "review_labels.csv"),
        "reviewed_label_summary_json": os.path.join(phase8_batch_dir, "reviewed_label_summary.json"),
        "reviewed_label_summary_md": os.path.join(phase8_batch_dir, "reviewed_label_summary.md"),
    }

    # Challenger trial
    if phase8b_trial_dir:
        manifest["challenger_trials"]["phase8b_trial_20260310"] = {
            "dir": phase8b_trial_dir,
            "policy_trials_csv": os.path.join(phase8b_trial_dir, "policy_trials.csv"),
            "summary_json": os.path.join(phase8b_trial_dir, "challenger_vs_champion_summary.json"),
            "summary_md": os.path.join(phase8b_trial_dir, "challenger_vs_champion_summary.md"),
        }

    return manifest


def save_artifact_manifest(manifest: dict, output_path: str) -> None:
    """Save artifact manifest to JSON file."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Saved artifact manifest to %s", output_path)
