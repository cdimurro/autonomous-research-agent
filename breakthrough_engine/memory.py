"""Cross-run memory for duplicate detection and learning from past failures.

Lightweight implementation backed by the bt_candidates and bt_rejections tables.
"""

from __future__ import annotations

import sqlite3
from difflib import SequenceMatcher

from .models import CandidateHypothesis, CandidateStatus


class RunMemory:
    """Provides cross-run awareness for deduplication and failure pattern detection."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def get_prior_statements(
        self, domain: str, exclude_run_id: str = "", limit: int = 200
    ) -> list[str]:
        """Retrieve statements from prior candidates for deduplication.

        Excludes candidates from the current run to avoid self-matching.
        """
        try:
            if exclude_run_id:
                rows = self.db.execute(
                    "SELECT statement FROM bt_candidates WHERE domain=? AND run_id != ? ORDER BY created_at DESC LIMIT ?",
                    (domain, exclude_run_id, limit),
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT statement FROM bt_candidates WHERE domain=? ORDER BY created_at DESC LIMIT ?",
                    (domain, limit),
                ).fetchall()
            return [row[0] for row in rows]
        except Exception:
            return []

    def is_near_duplicate(
        self,
        candidate: CandidateHypothesis,
        threshold: float = 0.85,
        exclude_run_id: str = "",
    ) -> tuple[bool, str]:
        """Check if a candidate is a near-duplicate of any prior candidate.

        Excludes the current run's candidates from comparison.
        Returns (is_duplicate, reason).
        """
        priors = self.get_prior_statements(
            candidate.domain, exclude_run_id=exclude_run_id
        )
        for prior in priors:
            similarity = SequenceMatcher(
                None, candidate.statement.lower(), prior.lower()
            ).ratio()
            if similarity > threshold:
                return True, f"Near-duplicate (similarity={similarity:.2f}) of prior candidate"
        return False, ""

    def get_repeated_failure_modes(self, domain: str, limit: int = 50) -> dict[str, int]:
        """Count how often each rejection reason appears for a domain."""
        try:
            rows = self.db.execute(
                """SELECT rejection_reason, COUNT(*) as cnt
                   FROM bt_rejections
                   WHERE run_id IN (
                       SELECT id FROM bt_runs WHERE program_name LIKE ?
                   )
                   GROUP BY rejection_reason
                   ORDER BY cnt DESC
                   LIMIT ?""",
                (f"%{domain}%", limit),
            ).fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception:
            return {}

    def get_prior_candidate_count(self, domain: str) -> int:
        """Total number of prior candidates for this domain."""
        try:
            row = self.db.execute(
                "SELECT COUNT(*) FROM bt_candidates WHERE domain=?", (domain,)
            ).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0
