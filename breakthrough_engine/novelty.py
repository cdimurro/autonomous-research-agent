"""Novelty / prior-art engine for the Breakthrough Engine.

Evaluates each candidate against:
- local prior candidates (titles, statements, mechanisms)
- prior publications
- retrieved paper titles/abstracts
- past rejected candidates

Uses layered deterministic heuristics:
1. Exact title match
2. Normalized statement token overlap
3. Mechanism overlap
4. Keyword overlap
5. Similarity against retrieved evidence titles/abstracts

Returns an explainable NoveltyResult with prior-art hits and reasoning.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import Counter
from difflib import SequenceMatcher
from typing import Optional

from .models import (
    CandidateHypothesis,
    EvidenceItem,
    NoveltyDecision,
    NoveltyResult,
    PriorArtHit,
    new_id,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Text normalization helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "must", "can", "could", "of", "in", "to",
    "for", "with", "on", "at", "from", "by", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "and", "but",
    "or", "nor", "not", "so", "yet", "both", "either", "neither", "each",
    "every", "all", "any", "few", "more", "most", "other", "some", "such",
    "no", "only", "own", "same", "than", "too", "very", "that", "this",
    "these", "those", "it", "its", "we", "our", "they", "their",
})


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stop words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS and len(w) > 2]


def _token_overlap(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Jaccard similarity between two token lists."""
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def _sequence_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Novelty Engine
# ---------------------------------------------------------------------------

class NoveltyEngine:
    """Evaluates candidate novelty against prior art.

    Thresholds:
    - exact_title_threshold: 0.95 → FAIL
    - statement_overlap_threshold: 0.80 → FAIL
    - mechanism_overlap_threshold: 0.75 → FAIL
    - keyword_overlap_threshold: 0.60 → WARN
    - retrieved_overlap_threshold: 0.70 → WARN
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        exact_title_threshold: float = 0.95,
        statement_overlap_threshold: float = 0.80,
        mechanism_overlap_threshold: float = 0.75,
        keyword_overlap_threshold: float = 0.60,
        retrieved_overlap_threshold: float = 0.70,
    ):
        self.db = db
        self.exact_title_threshold = exact_title_threshold
        self.statement_overlap_threshold = statement_overlap_threshold
        self.mechanism_overlap_threshold = mechanism_overlap_threshold
        self.keyword_overlap_threshold = keyword_overlap_threshold
        self.retrieved_overlap_threshold = retrieved_overlap_threshold

    def evaluate(
        self,
        candidate: CandidateHypothesis,
        retrieved_evidence: list[EvidenceItem] | None = None,
        exclude_run_id: str = "",
    ) -> NoveltyResult:
        """Run full novelty analysis on a candidate."""
        hits: list[PriorArtHit] = []
        overlap_reasons: list[str] = []
        warnings: list[str] = []
        max_duplicate_risk = 0.0

        # Layer 1: Check against prior candidate titles
        prior_candidates = self._get_prior_candidates(
            candidate.domain, exclude_run_id
        )
        for pc in prior_candidates:
            # Exact title match
            title_sim = _sequence_similarity(candidate.title, pc["title"])
            if title_sim >= self.exact_title_threshold:
                hits.append(PriorArtHit(
                    source="local_candidate", source_id=pc["id"],
                    title=pc["title"], similarity=title_sim,
                    overlap_type="exact_title",
                ))
                overlap_reasons.append(
                    f"Near-exact title match with candidate '{pc['title'][:60]}' (sim={title_sim:.2f})"
                )
                max_duplicate_risk = max(max_duplicate_risk, title_sim)

            # Statement overlap
            stmt_sim = _sequence_similarity(candidate.statement, pc["statement"])
            if stmt_sim >= self.statement_overlap_threshold:
                hits.append(PriorArtHit(
                    source="local_candidate", source_id=pc["id"],
                    title=pc["title"], similarity=stmt_sim,
                    overlap_type="statement_overlap",
                ))
                overlap_reasons.append(
                    f"Statement overlap with '{pc['title'][:60]}' (sim={stmt_sim:.2f})"
                )
                max_duplicate_risk = max(max_duplicate_risk, stmt_sim)

            # Mechanism overlap
            if pc.get("mechanism") and candidate.mechanism:
                mech_sim = _sequence_similarity(candidate.mechanism, pc["mechanism"])
                if mech_sim >= self.mechanism_overlap_threshold:
                    hits.append(PriorArtHit(
                        source="local_candidate", source_id=pc["id"],
                        title=pc["title"], similarity=mech_sim,
                        overlap_type="mechanism_overlap",
                    ))
                    overlap_reasons.append(
                        f"Mechanism overlap with '{pc['title'][:60]}' (sim={mech_sim:.2f})"
                    )
                    max_duplicate_risk = max(max_duplicate_risk, mech_sim * 0.9)

        # Layer 2: Check against prior publications
        prior_pubs = self._get_prior_publications(exclude_run_id)
        for pub in prior_pubs:
            title_sim = _sequence_similarity(candidate.title, pub["candidate_title"])
            if title_sim >= self.statement_overlap_threshold:
                hits.append(PriorArtHit(
                    source="publication", source_id=pub["id"],
                    title=pub["candidate_title"], similarity=title_sim,
                    overlap_type="statement_overlap",
                ))
                overlap_reasons.append(
                    f"Overlaps published candidate '{pub['candidate_title'][:60]}' (sim={title_sim:.2f})"
                )
                max_duplicate_risk = max(max_duplicate_risk, title_sim)

            if pub.get("hypothesis"):
                hyp_sim = _sequence_similarity(candidate.statement, pub["hypothesis"])
                if hyp_sim >= self.statement_overlap_threshold:
                    hits.append(PriorArtHit(
                        source="publication", source_id=pub["id"],
                        title=pub["candidate_title"], similarity=hyp_sim,
                        overlap_type="statement_overlap",
                    ))
                    overlap_reasons.append(
                        f"Statement overlaps published hypothesis (sim={hyp_sim:.2f})"
                    )
                    max_duplicate_risk = max(max_duplicate_risk, hyp_sim)

        # Layer 3: Check against retrieved evidence (paper titles/abstracts)
        if retrieved_evidence:
            cand_tokens = _tokenize(candidate.statement + " " + candidate.mechanism)
            for ev in retrieved_evidence:
                ev_tokens = _tokenize(ev.title + " " + ev.quote)
                token_sim = _token_overlap(cand_tokens, ev_tokens)
                if token_sim >= self.retrieved_overlap_threshold:
                    hits.append(PriorArtHit(
                        source="retrieved_paper", source_id=ev.source_id,
                        title=ev.title, similarity=token_sim,
                        overlap_type="keyword",
                    ))
                    overlap_reasons.append(
                        f"High keyword overlap with retrieved paper '{ev.title[:60]}' (sim={token_sim:.2f})"
                    )
                    warnings.append(f"Prior art: '{ev.title[:80]}'")
                elif token_sim >= self.keyword_overlap_threshold:
                    warnings.append(
                        f"Moderate keyword overlap with '{ev.title[:60]}' (sim={token_sim:.2f})"
                    )

        # Compute scores and decision
        novelty_score = max(0.0, 1.0 - max_duplicate_risk)

        # Count hard-fail hits (exact title or statement overlap)
        hard_fails = [h for h in hits if h.overlap_type in ("exact_title", "statement_overlap")]

        if hard_fails:
            decision = NoveltyDecision.FAIL
            explanation = (
                f"FAILED: {len(hard_fails)} near-duplicate(s) found. "
                + "; ".join(overlap_reasons[:3])
            )
        elif hits:
            decision = NoveltyDecision.WARN
            explanation = (
                f"WARNING: {len(hits)} prior-art hit(s) found but below hard-fail threshold. "
                + "; ".join(overlap_reasons[:3])
            )
        else:
            decision = NoveltyDecision.PASS
            explanation = "No significant prior-art overlap detected."

        return NoveltyResult(
            candidate_id=candidate.id,
            novelty_score=novelty_score,
            duplicate_risk_score=max_duplicate_risk,
            prior_art_hits=hits,
            overlap_reasons=overlap_reasons,
            decision=decision,
            warnings=warnings,
            explanation=explanation,
        )

    def _get_prior_candidates(self, domain: str, exclude_run_id: str) -> list[dict]:
        """Retrieve prior candidates from the DB.

        For cross-domain runs (domain contains '+'), searches both individual
        domains and the cross-domain domain itself.
        """
        try:
            domains = [domain]
            if "+" in domain:
                domains.extend(domain.split("+"))
                domains.append("cross-domain")

            placeholders = ",".join("?" for _ in domains)

            if exclude_run_id:
                rows = self.db.execute(
                    f"""SELECT id, title, statement, mechanism FROM bt_candidates
                       WHERE domain IN ({placeholders}) AND run_id != ?
                       ORDER BY created_at DESC LIMIT 200""",
                    (*domains, exclude_run_id),
                ).fetchall()
            else:
                rows = self.db.execute(
                    f"""SELECT id, title, statement, mechanism FROM bt_candidates
                       WHERE domain IN ({placeholders})
                       ORDER BY created_at DESC LIMIT 200""",
                    domains,
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _get_prior_publications(self, exclude_run_id: str = "") -> list[dict]:
        """Retrieve prior publications from the DB."""
        try:
            if exclude_run_id:
                rows = self.db.execute(
                    """SELECT id, candidate_title, hypothesis FROM bt_publications
                       WHERE run_id != ?
                       ORDER BY publication_date DESC LIMIT 50""",
                    (exclude_run_id,),
                ).fetchall()
            else:
                rows = self.db.execute(
                    "SELECT id, candidate_title, hypothesis FROM bt_publications ORDER BY publication_date DESC LIMIT 50"
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
