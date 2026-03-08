"""Operator review workflow for publication drafts.

In production_review mode, the orchestrator creates a PublicationDraft
instead of auto-publishing. An operator must explicitly approve or reject
the draft before a final PublicationRecord is created.

This preserves the one-publication-per-run invariant while adding
a safety gate for live production use.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from .db import Repository
from .models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    DraftStatus,
    EvidencePack,
    NoveltyResult,
    PublicationDraft,
    PublicationRecord,
    ReviewAction,
    ReviewEvent,
    SimulationResult,
    new_id,
)

logger = logging.getLogger(__name__)


def create_draft(
    repo: Repository,
    run_id: str,
    candidate: CandidateHypothesis,
    score: CandidateScore,
    evidence_pack: Optional[EvidencePack] = None,
    simulation_result: Optional[SimulationResult] = None,
    novelty_result: Optional[NoveltyResult] = None,
) -> PublicationDraft:
    """Create a publication draft pending operator review."""
    evidence_summary = _format_evidence(evidence_pack)
    sim_summary = _format_sim(simulation_result)
    novelty_summary = _format_novelty(novelty_result)

    draft = PublicationDraft(
        run_id=run_id,
        candidate_id=candidate.id,
        candidate_title=candidate.title,
        abstract=f"Breakthrough candidate in {candidate.domain}: {candidate.statement[:200]}",
        hypothesis=candidate.statement,
        score_breakdown=score.model_dump(),
        evidence_summary=evidence_summary,
        simulation_summary=sim_summary,
        novelty_summary=novelty_summary,
        assumptions=candidate.assumptions,
        uncertainties=candidate.risk_flags,
        replication_priority="high" if score.final_score > 0.8 else "medium",
        status=DraftStatus.PENDING_REVIEW,
    )
    repo.save_draft(draft)
    repo.update_candidate_status(candidate.id, CandidateStatus.DRAFT_PENDING_REVIEW)
    logger.info("Created publication draft %s for candidate '%s'", draft.id, candidate.title)
    return draft


def approve_draft(
    repo: Repository,
    draft_id: str,
    reviewer: str = "operator",
    notes: str = "",
) -> Optional[PublicationRecord]:
    """Approve a draft and create the final publication.

    Returns the PublicationRecord or None if draft not found / already reviewed.
    """
    draft = repo.get_draft(draft_id)
    if not draft:
        logger.warning("Draft %s not found", draft_id)
        return None

    if draft["status"] != DraftStatus.PENDING_REVIEW.value:
        logger.warning("Draft %s already reviewed (status=%s)", draft_id, draft["status"])
        return None

    # Check one-publication-per-run invariant
    run = repo.get_run(draft["run_id"])
    if run and run.get("publication_id"):
        logger.warning("Run %s already has a publication", draft["run_id"])
        return None

    # Update draft status
    repo.update_draft_status(draft_id, DraftStatus.APPROVED)

    # Record review event
    event = ReviewEvent(
        draft_id=draft_id,
        run_id=draft["run_id"],
        candidate_id=draft["candidate_id"],
        action=ReviewAction.APPROVE,
        reviewer=reviewer,
        notes=notes,
    )
    repo.save_review_event(event)

    # Create final publication
    import json
    score_data = draft.get("score_breakdown", "{}")
    if isinstance(score_data, str):
        try:
            score_data = json.loads(score_data)
        except (json.JSONDecodeError, TypeError):
            score_data = {}

    assumptions = draft.get("assumptions", "[]")
    if isinstance(assumptions, str):
        try:
            assumptions = json.loads(assumptions)
        except (json.JSONDecodeError, TypeError):
            assumptions = []

    uncertainties = draft.get("uncertainties", "[]")
    if isinstance(uncertainties, str):
        try:
            uncertainties = json.loads(uncertainties)
        except (json.JSONDecodeError, TypeError):
            uncertainties = []

    pub = PublicationRecord(
        run_id=draft["run_id"],
        candidate_id=draft["candidate_id"],
        candidate_title=draft["candidate_title"],
        abstract=draft.get("abstract", ""),
        hypothesis=draft["hypothesis"],
        score_breakdown=score_data,
        evidence_summary=draft.get("evidence_summary", ""),
        simulation_summary=draft.get("simulation_summary", ""),
        assumptions=assumptions,
        uncertainties=uncertainties,
        replication_priority=draft.get("replication_priority", "medium"),
    )
    repo.save_publication(pub)

    # Update candidate and run
    repo.update_candidate_status(draft["candidate_id"], CandidateStatus.PUBLISHED)
    repo.db.execute(
        "UPDATE bt_runs SET publication_id=? WHERE id=?",
        (pub.id, draft["run_id"]),
    )
    repo.db.commit()

    logger.info("Draft %s approved → publication %s", draft_id, pub.id)
    return pub


def reject_draft(
    repo: Repository,
    draft_id: str,
    reviewer: str = "operator",
    reason: str = "",
) -> bool:
    """Reject a draft. Returns True if successful."""
    draft = repo.get_draft(draft_id)
    if not draft:
        logger.warning("Draft %s not found", draft_id)
        return False

    if draft["status"] != DraftStatus.PENDING_REVIEW.value:
        logger.warning("Draft %s already reviewed (status=%s)", draft_id, draft["status"])
        return False

    repo.update_draft_status(draft_id, DraftStatus.REJECTED)

    event = ReviewEvent(
        draft_id=draft_id,
        run_id=draft["run_id"],
        candidate_id=draft["candidate_id"],
        action=ReviewAction.REJECT,
        reviewer=reviewer,
        notes=reason,
    )
    repo.save_review_event(event)

    # Update candidate status back to publication_failed
    repo.update_candidate_status(
        draft["candidate_id"],
        CandidateStatus.PUBLICATION_FAILED,
        f"Draft rejected by {reviewer}: {reason}",
    )

    logger.info("Draft %s rejected by %s: %s", draft_id, reviewer, reason)
    return True


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_evidence(pack: Optional[EvidencePack]) -> str:
    if not pack or not pack.items:
        return "No evidence attached."
    lines = []
    for i, item in enumerate(pack.items, 1):
        lines.append(f"{i}. [{item.citation}] \"{item.quote[:150]}...\"")
    return "\n".join(lines)


def _format_sim(result: Optional[SimulationResult]) -> str:
    if not result:
        return "Not simulated."
    return f"Status: {result.status.value}. {result.pass_fail_summary}"


def _format_novelty(result: Optional[NoveltyResult]) -> str:
    if not result:
        return "Novelty not evaluated."
    parts = [f"Novelty: {result.decision.value} (score={result.novelty_score:.2f})"]
    if result.prior_art_hits:
        parts.append(f"{len(result.prior_art_hits)} prior-art hit(s)")
    if result.explanation:
        parts.append(result.explanation)
    return ". ".join(parts)
