"""Evidence grounding validation for generated hypotheses.

Phase 10E: Checks whether cited/attached evidence actually supports
the proposed hypothesis claim. Detects hallucinated or weakly grounded
hypotheses.

Validation levels:
- strong_support: evidence directly supports the claim
- weak_support: evidence is related but doesn't directly support
- unsupported: no meaningful connection between evidence and claim
- contradicted: evidence appears to contradict the claim
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from .models import CandidateHypothesis, EvidenceItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Grounding result
# ---------------------------------------------------------------------------

@dataclass
class GroundingResult:
    """Result of validating evidence grounding for a candidate."""
    candidate_id: str = ""
    candidate_title: str = ""
    overall_verdict: str = "unsupported"  # strong_support | weak_support | unsupported | contradicted
    evidence_verdicts: dict[str, str] = field(default_factory=dict)  # evidence_id -> verdict
    evidence_scores: dict[str, float] = field(default_factory=dict)  # evidence_id -> score
    grounding_score: float = 0.0  # 0-1 aggregate
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "candidate_title": self.candidate_title,
            "overall_verdict": self.overall_verdict,
            "grounding_score": round(self.grounding_score, 4),
            "evidence_count": len(self.evidence_verdicts),
            "verdicts": self.evidence_verdicts,
            "scores": {k: round(v, 4) for k, v in self.evidence_scores.items()},
            "explanation": self.explanation,
        }


# ---------------------------------------------------------------------------
# Keyword-based grounding validator
# ---------------------------------------------------------------------------

def _extract_claim_keywords(candidate: CandidateHypothesis) -> set[str]:
    """Extract meaningful keywords from the candidate's claims."""
    text = f"{candidate.statement} {candidate.mechanism} {candidate.expected_outcome}"
    # Remove stopwords and extract content words
    words = set(re.findall(r'\b[a-z]{3,}\b', text.lower()))
    stopwords = {
        "the", "and", "that", "this", "with", "from", "have", "has", "had",
        "are", "was", "were", "been", "will", "would", "could", "should",
        "may", "can", "for", "not", "but", "its", "our", "their", "each",
        "which", "when", "where", "what", "how", "than", "then", "also",
        "more", "most", "such", "into", "over", "under", "between", "through",
        "about", "after", "before", "during", "these", "those", "some",
    }
    return words - stopwords


def _extract_evidence_keywords(item: EvidenceItem) -> set[str]:
    """Extract meaningful keywords from evidence."""
    text = f"{item.title} {item.quote}"
    words = set(re.findall(r'\b[a-z]{3,}\b', text.lower()))
    return words


def _keyword_overlap_score(claim_kw: set[str], evidence_kw: set[str]) -> float:
    """Compute Jaccard-like overlap between claim and evidence keywords."""
    if not claim_kw or not evidence_kw:
        return 0.0
    intersection = len(claim_kw & evidence_kw)
    # Normalize by claim keywords (what fraction of the claim is supported)
    return min(1.0, intersection / max(1, len(claim_kw)) * 3.0)


# Contradiction signals
_CONTRADICTION_PATTERNS = [
    re.compile(r'\b(fail|failed|disproven|refuted|incorrect|impossible)\b', re.I),
    re.compile(r'\b(no\s+effect|no\s+improvement|no\s+evidence)\b', re.I),
    re.compile(r'\b(contrary|opposite|reverse|decrease|degrade)\b', re.I),
]


def _check_contradiction(candidate_text: str, evidence_text: str) -> bool:
    """Simple check for contradiction signals in evidence relative to claim."""
    # Very conservative — only flag if evidence contains strong negation words
    # AND they relate to terms in the candidate
    for pat in _CONTRADICTION_PATTERNS:
        if pat.search(evidence_text):
            # Check if the negation is about something the candidate claims
            claim_words = set(re.findall(r'\b\w{4,}\b', candidate_text.lower()))
            neg_context = evidence_text[max(0, pat.search(evidence_text).start() - 50):
                                        pat.search(evidence_text).end() + 50].lower()
            overlap = len(claim_words & set(re.findall(r'\b\w{4,}\b', neg_context)))
            if overlap >= 2:
                return True
    return False


class EvidenceGroundingValidator:
    """Validates whether evidence actually supports generated hypotheses.

    Uses keyword overlap, source-type trust priors, and contradiction
    detection. Does NOT use LLM calls — fully offline-safe.
    """

    # Trust priors by source type
    SOURCE_TRUST_PRIORS: dict[str, float] = {
        "finding": 0.90,       # curated, accepted findings
        "paper": 0.85,         # direct paper citations
        "kg_segment": 0.70,    # machine-extracted segments
        "kg_graph": 0.60,      # graph-derived entity/relation
        "graph_path": 0.55,    # multi-hop reasoning paths
        "kg_synthesis": 0.50,  # cross-paper synthesis
        "kg_subgraph": 0.52,   # subgraph-derived evidence
    }

    def __init__(self, trust_priors: Optional[dict[str, float]] = None):
        self.trust_priors = trust_priors or dict(self.SOURCE_TRUST_PRIORS)

    def validate(
        self,
        candidate: CandidateHypothesis,
        evidence: list[EvidenceItem],
    ) -> GroundingResult:
        """Validate grounding of a candidate against its evidence.

        Phase 10E-Prime: graph-path evidence gets a structural coherence
        bonus when the path concepts overlap with the claim.
        """
        result = GroundingResult(
            candidate_id=candidate.id,
            candidate_title=candidate.title,
        )

        if not evidence:
            result.overall_verdict = "unsupported"
            result.explanation = "No evidence items provided."
            return result

        claim_kw = _extract_claim_keywords(candidate)
        candidate_text = f"{candidate.statement} {candidate.mechanism}"

        scores: list[float] = []

        for item in evidence:
            evidence_kw = _extract_evidence_keywords(item)
            overlap = _keyword_overlap_score(claim_kw, evidence_kw)

            # Apply source trust prior
            trust = self.trust_priors.get(item.source_type, 0.5)
            grounding = overlap * 0.6 + trust * 0.2 + item.relevance_score * 0.2

            # Phase 10E-Prime: structural coherence bonus for graph evidence
            # Graph paths that contain claim-relevant concepts are more
            # trustworthy than random graph traversals
            if item.source_type in ("graph_path", "kg_synthesis", "kg_subgraph"):
                if overlap > 0.3:
                    grounding = min(1.0, grounding + 0.05)

            # Check for contradiction
            evidence_text = f"{item.title} {item.quote}"
            if _check_contradiction(candidate_text, evidence_text):
                grounding *= 0.3  # heavy penalty
                result.evidence_verdicts[item.id] = "contradicted"
            elif grounding >= 0.5:
                result.evidence_verdicts[item.id] = "strong_support"
            elif grounding >= 0.3:
                result.evidence_verdicts[item.id] = "weak_support"
            else:
                result.evidence_verdicts[item.id] = "unsupported"

            result.evidence_scores[item.id] = grounding
            scores.append(grounding)

        # Aggregate
        if scores:
            result.grounding_score = sum(scores) / len(scores)

        # Overall verdict
        strong = sum(1 for v in result.evidence_verdicts.values() if v == "strong_support")
        contradicted = sum(1 for v in result.evidence_verdicts.values() if v == "contradicted")

        if contradicted > 0 and contradicted >= strong:
            result.overall_verdict = "contradicted"
            result.explanation = f"{contradicted} evidence items show contradiction signals."
        elif strong >= max(1, len(evidence) * 0.3):
            result.overall_verdict = "strong_support"
            result.explanation = f"{strong}/{len(evidence)} evidence items strongly support the claim."
        elif result.grounding_score >= 0.3:
            result.overall_verdict = "weak_support"
            result.explanation = f"Mean grounding score {result.grounding_score:.2f}; partial keyword overlap."
        else:
            result.overall_verdict = "unsupported"
            result.explanation = f"Mean grounding score {result.grounding_score:.2f}; insufficient evidence overlap."

        logger.info(
            "GroundingValidation: candidate=%s verdict=%s score=%.3f strong=%d/%d",
            candidate.id[:8], result.overall_verdict, result.grounding_score,
            strong, len(evidence),
        )
        return result
