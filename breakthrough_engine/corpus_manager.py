"""Novelty corpus management for the Breakthrough Engine.

Phase 4D addition. Manages the set of candidates that are active in the
novelty corpus vs archived. Archival prevents old, dense regions from
permanently blocking new candidates in similar (but not identical) areas.

Key design decisions:
- Archival is ADDITIVE: archived candidates are NOT used for embedding novelty checks.
- Archival does NOT weaken the novelty thresholds. It compresses the active corpus.
- The NoveltyEngine checks only active (non-archived) candidates.
- Archived candidates remain in the DB for audit/analysis.

Archival triggers:
- Age: candidate older than N days and has status != published
- Cluster saturation: if >K candidates have near-identical embeddings, archive oldest

Provides:
- CorpusManager: manages active/archived candidate sets
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How many days before a non-published candidate is eligible for archival
DEFAULT_ARCHIVE_AGE_DAYS = 30

# If a cluster has more than this many candidates, archive oldest until at threshold
DEFAULT_CLUSTER_SATURATION_LIMIT = 5

# Statuses that are NEVER archived (final/published outcomes)
PROTECTED_STATUSES = {"published", "draft_pending_review"}


# ---------------------------------------------------------------------------
# CorpusManager
# ---------------------------------------------------------------------------


class CorpusManager:
    """Manages active vs archived novelty corpus.

    Works directly with the Repository to:
    1. Archive old non-published candidates to reduce corpus density.
    2. Archive cluster-saturated candidates.
    3. Expose is_active() for the NoveltyEngine to check before including a candidate.
    """

    def __init__(self, repo, archive_age_days: int = DEFAULT_ARCHIVE_AGE_DAYS):
        self._repo = repo
        self.archive_age_days = archive_age_days

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_active(self, candidate_id: str) -> bool:
        """Return True if this candidate is active (not archived)."""
        return not self._repo.is_archived(candidate_id)

    def run_archival(self, domain: str) -> dict:
        """Run all archival passes for a domain. Returns stats dict."""
        age_count = self._archive_old_candidates(domain)
        return {
            "domain": domain,
            "archived_by_age": age_count,
            "total_archived": age_count,
        }

    def archive_by_cluster(
        self,
        domain: str,
        cluster_candidates: list[str],
        cluster_id: str,
        keep_newest: int = DEFAULT_CLUSTER_SATURATION_LIMIT,
    ) -> int:
        """Archive oldest candidates in a saturated cluster, keeping `keep_newest` newest.

        Returns number of candidates archived.
        """
        if len(cluster_candidates) <= keep_newest:
            return 0

        # cluster_candidates should be ordered oldest-first
        to_archive = cluster_candidates[:-keep_newest]
        count = 0
        for cid in to_archive:
            if not self._repo.is_archived(cid):
                # Check if protected
                cand = self._get_candidate_status(cid)
                if cand and cand.get("status") in PROTECTED_STATUSES:
                    continue
                self._repo.archive_candidate(cid, domain, "cluster_saturation", cluster_id)
                count += 1
                logger.debug("Archived candidate %s (cluster_saturation, cluster=%s)", cid, cluster_id)

        return count

    def get_active_count(self, domain: str) -> int:
        """Count active (non-archived) candidates for a domain."""
        try:
            archived_ids = {
                r["candidate_id"]
                for r in self._repo.list_archived_candidates(domain, limit=2000)
            }
            rows = self._repo.db.execute(
                "SELECT COUNT(*) FROM bt_candidates WHERE domain=?", (domain,)
            ).fetchone()
            total = rows[0] if rows else 0
            return total - len(archived_ids)
        except Exception as e:
            logger.warning("Could not count active candidates: %s", e)
            return -1

    def get_active_candidate_ids(self, domain: str, limit: int = 200) -> set[str]:
        """Return set of active (non-archived) candidate IDs for a domain."""
        try:
            all_rows = self._repo.db.execute(
                "SELECT id FROM bt_candidates WHERE domain=? ORDER BY created_at DESC LIMIT ?",
                (domain, limit + 500),  # fetch extra to account for archived ones
            ).fetchall()
            archived_ids = {
                r["candidate_id"]
                for r in self._repo.list_archived_candidates(domain, limit=2000)
            }
            active = []
            for row in all_rows:
                if row["id"] not in archived_ids:
                    active.append(row["id"])
                    if len(active) >= limit:
                        break
            return set(active)
        except Exception as e:
            logger.warning("Could not get active candidate IDs: %s", e)
            return set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _archive_old_candidates(self, domain: str) -> int:
        """Archive candidates older than archive_age_days that are non-protected."""
        try:
            cutoff = self._days_ago_str(self.archive_age_days)
            rows = self._repo.db.execute(
                """SELECT id, status FROM bt_candidates
                   WHERE domain=? AND created_at < ?
                   ORDER BY created_at ASC""",
                (domain, cutoff),
            ).fetchall()

            count = 0
            for row in rows:
                cid = row["id"]
                status = row["status"]
                if status in PROTECTED_STATUSES:
                    continue
                if self._repo.is_archived(cid):
                    continue
                self._repo.archive_candidate(cid, domain, "recency", "")
                count += 1
                logger.debug("Archived candidate %s (recency, domain=%s)", cid, domain)

            return count
        except Exception as e:
            logger.warning("Age-based archival failed for domain=%s: %s", domain, e)
            return 0

    def _get_candidate_status(self, candidate_id: str) -> dict | None:
        try:
            row = self._repo.db.execute(
                "SELECT id, status FROM bt_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    @staticmethod
    def _days_ago_str(days: int) -> str:
        from datetime import timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=days)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
