"""Review-label completeness tooling for the Breakthrough Engine Phase 8.

Makes it easy to identify which champions and runner-up finalists in a batch
are missing review labels so a reviewer can fill them efficiently.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LabelTarget:
    """A candidate that needs a review label."""
    campaign_id: str
    candidate_id: str
    candidate_title: str
    candidate_role: str         # champion | runner_up | finalist
    final_score: float = 0.0
    has_label: bool = False
    label_decision: Optional[str] = None   # approve | reject | defer | None

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "candidate_id": self.candidate_id,
            "candidate_title": self.candidate_title,
            "candidate_role": self.candidate_role,
            "final_score": round(self.final_score, 5),
            "has_label": self.has_label,
            "label_decision": self.label_decision,
        }


@dataclass
class LabelCompleteness:
    """Summary of label completeness for a set of campaigns."""
    campaign_ids: list = field(default_factory=list)
    total_targets: int = 0          # champions + expected runner-ups
    labeled_targets: int = 0
    unlabeled_targets: int = 0
    completion_rate: float = 0.0
    is_complete: bool = False       # True when all champions + runner-ups are labeled
    targets: list = field(default_factory=list)  # list of LabelTarget
    missing: list = field(default_factory=list)  # list of LabelTarget (unlabeled only)

    def to_dict(self) -> dict:
        return {
            "campaign_ids": self.campaign_ids,
            "total_targets": self.total_targets,
            "labeled_targets": self.labeled_targets,
            "unlabeled_targets": self.unlabeled_targets,
            "completion_rate": round(self.completion_rate, 3),
            "is_complete": self.is_complete,
            "missing": [t.to_dict() for t in self.missing],
        }


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def check_label_completeness(
    db,
    campaign_ids: list[str],
) -> LabelCompleteness:
    """Check review-label completeness for a list of campaign IDs.

    For each campaign, the following are required:
    - Champion: exactly 1 label required
    - Runner-up (rank 2 finalist by score): 1 label expected

    Args:
        db: sqlite3 connection with row_factory = sqlite3.Row
        campaign_ids: list of campaign IDs to check

    Returns:
        LabelCompleteness summary with missing targets
    """
    all_targets: list[LabelTarget] = []
    missing: list[LabelTarget] = []

    for campaign_id in campaign_ids:
        # Get finalists for this campaign ordered by score descending
        finalists = _get_finalists_for_campaign(db, campaign_id)

        # Get existing labels for this campaign
        labeled_ids = _get_labeled_candidate_ids(db, campaign_id)

        # Champion = rank 1
        if finalists:
            champ = finalists[0]
            target = LabelTarget(
                campaign_id=campaign_id,
                candidate_id=champ["id"],
                candidate_title=champ["title"],
                candidate_role="champion",
                final_score=champ.get("final_score", 0.0),
                has_label=champ["id"] in labeled_ids,
                label_decision=labeled_ids.get(champ["id"]),
            )
            all_targets.append(target)
            if not target.has_label:
                missing.append(target)

        # Runner-up = rank 2
        if len(finalists) >= 2:
            runner = finalists[1]
            target = LabelTarget(
                campaign_id=campaign_id,
                candidate_id=runner["id"],
                candidate_title=runner["title"],
                candidate_role="runner_up",
                final_score=runner.get("final_score", 0.0),
                has_label=runner["id"] in labeled_ids,
                label_decision=labeled_ids.get(runner["id"]),
            )
            all_targets.append(target)
            if not target.has_label:
                missing.append(target)

    total = len(all_targets)
    labeled = total - len(missing)
    completion = labeled / total if total > 0 else 0.0

    return LabelCompleteness(
        campaign_ids=campaign_ids,
        total_targets=total,
        labeled_targets=labeled,
        unlabeled_targets=len(missing),
        completion_rate=completion,
        is_complete=len(missing) == 0 and total > 0,
        targets=all_targets,
        missing=missing,
    )


def _get_finalists_for_campaign(db, campaign_id: str) -> list[dict]:
    """Get finalists (shortlisted candidates) for a campaign, ordered by score desc.

    Tries multiple sources in order:
    1. Evaluation pack finalists CSV (most reliable for batch campaigns)
    2. bt_campaign_receipts (champion + at least one target)
    3. bt_stage_events table (if available)
    4. bt_candidates fallback
    """
    # Try evaluation pack first — most reliable for eval-grade campaigns
    finalists = _get_finalists_from_eval_pack(campaign_id)
    if finalists:
        return finalists

    try:
        # Try bt_campaign_receipts for champion info
        receipt_row = db.execute(
            "SELECT * FROM bt_campaign_receipts WHERE campaign_id=? LIMIT 1",
            (campaign_id,),
        ).fetchone()

        if receipt_row:
            d = dict(receipt_row)
            champion_id = d.get("champion_candidate_id", "")
            champion_title = d.get("champion_candidate_title", "")
            if champion_id:
                return [{"id": champion_id, "title": champion_title, "final_score": 0.0}]

        # Try bt_stage_events if available
        try:
            stage_rows = db.execute(
                """SELECT * FROM bt_stage_events
                   WHERE campaign_id=? AND event_type='finalist_selected'
                   ORDER BY created_at ASC""",
                (campaign_id,),
            ).fetchall()
            stage_finalists = []
            for row in stage_rows:
                d = dict(row)
                details = json.loads(d.get("details_json") or "{}")
                stage_finalists.append({
                    "id": details.get("candidate_id", d.get("candidate_id", "")),
                    "title": details.get("title", details.get("candidate_title", "")),
                    "final_score": details.get("final_score", details.get("score", 0.0)),
                })
            if stage_finalists:
                stage_finalists.sort(key=lambda x: x["final_score"], reverse=True)
                return stage_finalists
        except Exception:
            pass

    except Exception as e:
        logger.debug("Could not get finalists for campaign %s: %s", campaign_id, e)

    return []


def _get_finalists_from_eval_pack(campaign_id: str) -> list[dict]:
    """Read finalists from the evaluation pack finalists CSV or JSON if it exists."""
    import csv as _csv

    runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
    csv_path = os.path.join(runtime_root, "evaluation_packs", campaign_id, "finalists.csv")
    json_path = os.path.join(runtime_root, "evaluation_packs", campaign_id, "evaluation_pack.json")

    # Try CSV first
    if os.path.exists(csv_path):
        try:
            with open(csv_path, newline="") as f:
                reader = _csv.DictReader(f)
                finalists = []
                for row in reader:
                    score = 0.0
                    try:
                        score = float(row.get("final_score", 0) or 0)
                    except (TypeError, ValueError):
                        pass
                    cid = row.get("candidate_id", row.get("id", ""))
                    title = row.get("title", "")
                    if cid:
                        finalists.append({"id": cid, "title": title, "final_score": score})
            finalists.sort(key=lambda x: x["final_score"], reverse=True)
            return finalists
        except Exception as e:
            logger.debug("Could not read finalists CSV for %s: %s", campaign_id, e)

    # Try JSON pack
    if os.path.exists(json_path):
        try:
            with open(json_path) as f:
                pack = json.load(f)
            fins_data = pack.get("finalists", [])
            if fins_data:
                result = []
                for item in fins_data:
                    result.append({
                        "id": item.get("candidate_id", item.get("id", "")),
                        "title": item.get("title", ""),
                        "final_score": float(item.get("final_score", 0) or 0),
                    })
                result.sort(key=lambda x: x["final_score"], reverse=True)
                return result
        except Exception as e:
            logger.debug("Could not read finalists JSON for %s: %s", campaign_id, e)

    return []


def _get_labeled_candidate_ids(db, campaign_id: str) -> dict[str, str]:
    """Return {candidate_id: decision} for all labeled candidates in this campaign."""
    try:
        rows = db.execute(
            "SELECT candidate_id, decision FROM bt_review_labels WHERE campaign_id=?",
            (campaign_id,),
        ).fetchall()
        return {r["candidate_id"]: r["decision"] for r in rows}
    except Exception as e:
        logger.debug("Could not get review labels for campaign %s: %s", campaign_id, e)
        return {}


def export_label_targets_csv(
    completeness: LabelCompleteness,
    output_path: Optional[str] = None,
) -> str:
    """Export unlabeled targets to a CSV string or file.

    Returns the CSV content as a string.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "campaign_id", "candidate_id", "candidate_title",
        "candidate_role", "final_score", "has_label", "label_decision",
        "# Add label command",
    ])

    for target in completeness.targets:
        cmd = (
            f".venv/bin/python -m breakthrough_engine review-label add "
            f"--campaign-id {target.campaign_id} "
            f"--candidate-id {target.candidate_id} "
            f"--role {target.candidate_role} "
            f"--decision defer "
            f"--novelty-confidence 0.5 "
            f"--technical-plausibility 0.5 "
            f"--commercialization-relevance 0.5"
        )
        writer.writerow([
            target.campaign_id,
            target.candidate_id,
            target.candidate_title,
            target.candidate_role,
            target.final_score,
            target.has_label,
            target.label_decision or "",
            cmd if not target.has_label else "",
        ])

    content = output.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(content)
        logger.info("Exported label targets to %s", output_path)

    return content


def summarize_label_completeness(completeness: LabelCompleteness) -> str:
    """Return a human-readable summary of label completeness."""
    lines = [
        f"Label Completeness Summary",
        f"==========================",
        f"Campaigns: {len(completeness.campaign_ids)}",
        f"Total label targets (champion + runner-up): {completeness.total_targets}",
        f"Labeled: {completeness.labeled_targets}",
        f"Missing: {completeness.unlabeled_targets}",
        f"Completion rate: {completeness.completion_rate:.1%}",
        f"Is complete: {completeness.is_complete}",
        "",
    ]

    if completeness.missing:
        lines.append("Missing labels:")
        for t in completeness.missing:
            lines.append(
                f"  [{t.candidate_role.upper()}] {t.campaign_id[:8]}... "
                f"'{t.candidate_title[:60]}' (score={t.final_score:.3f})"
            )
    else:
        lines.append("All required labels are present.")

    return "\n".join(lines)


def get_label_summary_for_batch(db, batch_json: dict) -> dict:
    """Compute label completeness for a batch given its batch_summary.json content.

    Returns a dict suitable for inclusion in a batch report.
    """
    campaign_ids = [c["campaign_id"] for c in batch_json.get("campaigns", [])]
    completeness = check_label_completeness(db, campaign_ids)

    # Aggregate label stats
    total_labels = 0
    approve_count = 0
    reject_count = 0
    defer_count = 0

    try:
        rows = db.execute(
            "SELECT decision, COUNT(*) as cnt FROM bt_review_labels "
            "WHERE campaign_id IN ({}) GROUP BY decision".format(
                ",".join("?" * len(campaign_ids))
            ),
            campaign_ids,
        ).fetchall()
        for row in rows:
            d = row["decision"]
            c = row["cnt"]
            total_labels += c
            if d == "approve":
                approve_count = c
            elif d == "reject":
                reject_count = c
            elif d == "defer":
                defer_count = c
    except Exception as e:
        logger.debug("Could not aggregate label stats: %s", e)

    return {
        "total_labels": total_labels,
        "approve_count": approve_count,
        "reject_count": reject_count,
        "defer_count": defer_count,
        "approval_rate": approve_count / total_labels if total_labels > 0 else None,
        "completeness": completeness.to_dict(),
    }
