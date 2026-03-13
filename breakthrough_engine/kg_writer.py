"""KG write-back scaffolding for published candidates.

Phase 10A: Prepares future write-back of published candidates into
bt_kg_findings with temporal fields. Shadow-only — does not affect
policy learning or production scoring.

Temporal design:
- valid_from: when the finding was created
- valid_until: NULL means currently valid; set when superseded
- superseded_by: ID of the finding that replaces this one
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from .db import Repository
from .models import CandidateHypothesis, PublicationRecord, new_id

logger = logging.getLogger(__name__)


def write_candidate_as_finding(
    repo: Repository,
    candidate: CandidateHypothesis,
    publication_id: str = "",
    confidence: float = 0.5,
    evidence_ids: Optional[list[str]] = None,
    shadow: bool = True,
) -> str:
    """Write a published candidate into bt_kg_findings.

    Args:
        repo: Database repository
        candidate: The candidate hypothesis to write back
        publication_id: Optional publication ID if the candidate was published
        confidence: Confidence score for the finding
        evidence_ids: List of evidence IDs that supported this candidate
        shadow: If True, marks the finding as shadow (not policy-active)

    Returns:
        The finding ID.
    """
    finding_id = new_id()

    finding = {
        "id": finding_id,
        "candidate_id": candidate.id,
        "publication_id": publication_id,
        "title": candidate.title[:500],
        "statement": candidate.statement[:2000],
        "mechanism": candidate.mechanism[:2000],
        "domain": candidate.domain,
        "confidence": confidence,
        "source_evidence_ids": evidence_ids or candidate.evidence_refs,
        "status": "shadow" if shadow else "active",
    }

    repo.save_kg_finding(finding)

    logger.info(
        "KG write-back: finding=%s candidate=%s domain=%s shadow=%s",
        finding_id, candidate.id, candidate.domain, shadow,
    )
    return finding_id


def write_publication_as_finding(
    repo: Repository,
    publication: PublicationRecord,
    candidate: CandidateHypothesis,
    confidence: float = 0.7,
    shadow: bool = True,
) -> str:
    """Write a publication record as a KG finding.

    Higher confidence than raw candidates because publications have
    passed scoring, novelty, and harness gates.
    """
    return write_candidate_as_finding(
        repo=repo,
        candidate=candidate,
        publication_id=publication.id,
        confidence=confidence,
        evidence_ids=candidate.evidence_refs,
        shadow=shadow,
    )


def supersede_finding(
    repo: Repository,
    old_finding_id: str,
    new_finding_id: str,
) -> bool:
    """Mark an old finding as superseded by a new one.

    Sets valid_until and superseded_by on the old finding.
    Returns True if the update was applied.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        repo.db.execute(
            """UPDATE bt_kg_findings
               SET valid_until = ?, superseded_by = ?, status = 'superseded'
               WHERE id = ? AND valid_until IS NULL""",
            (now, new_finding_id, old_finding_id),
        )
        repo.db.commit()
        logger.info(
            "KG finding superseded: old=%s new=%s", old_finding_id, new_finding_id,
        )
        return True
    except Exception as e:
        logger.warning("Failed to supersede finding %s: %s", old_finding_id, e)
        return False


def list_active_findings(
    repo: Repository,
    domain: str = "",
    limit: int = 50,
) -> list[dict]:
    """List active (non-superseded) KG findings."""
    return repo.list_kg_findings(domain=domain, status="active", limit=limit)


def list_shadow_findings(
    repo: Repository,
    domain: str = "",
    limit: int = 50,
) -> list[dict]:
    """List shadow KG findings (write-back candidates not yet active)."""
    return repo.list_kg_findings(domain=domain, status="shadow", limit=limit)


# ---------------------------------------------------------------------------
# Phase 10E-Prime: Graph memory loop preparation
# ---------------------------------------------------------------------------

def generate_write_back_payload(
    candidate: CandidateHypothesis,
    publication_id: str = "",
    confidence: float = 0.5,
    grounding_verdict: str = "",
    grounding_score: float = 0.0,
    evidence_ids: Optional[list[str]] = None,
) -> dict:
    """Generate a write-back payload without persisting.

    Used for dry-run validation and readiness testing.
    The payload follows the bt_kg_findings schema with additional
    grounding metadata for the memory loop.
    """
    return {
        "id": new_id(),
        "candidate_id": candidate.id,
        "publication_id": publication_id,
        "title": candidate.title[:500],
        "statement": candidate.statement[:2000],
        "mechanism": candidate.mechanism[:2000],
        "domain": candidate.domain,
        "confidence": confidence,
        "source_evidence_ids": evidence_ids or candidate.evidence_refs,
        "grounding_verdict": grounding_verdict,
        "grounding_score": round(grounding_score, 4),
        "status": "shadow",
    }


def write_back_readiness_check(repo: Repository) -> dict:
    """Check whether the write-back path is ready for activation.

    Returns a readiness report without making any changes.
    """
    try:
        active = repo.list_kg_findings(status="active", limit=1)
        shadow = repo.list_kg_findings(status="shadow", limit=100)
        total = len(active) + len(shadow)
    except Exception:
        return {
            "ready": False,
            "reason": "bt_kg_findings table not accessible",
            "active_count": 0,
            "shadow_count": 0,
        }

    return {
        "ready": True,
        "reason": "Write-back path operational (shadow-only mode)",
        "active_count": len(active),
        "shadow_count": len(shadow),
        "total_findings": total,
        "activation_blocked": True,  # Phase 10E-Prime: not yet enabled
        "activation_reason": "Requires explicit promotion after downstream campaign validation",
    }
