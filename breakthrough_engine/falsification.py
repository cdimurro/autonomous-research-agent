"""Fast falsification lane for the Breakthrough Engine Phase 6.

Provides rule-based (no LLM) analysis to identify potential weaknesses
in shortlisted candidates:
- Contradiction search (evidence vs mechanism)
- Missing evidence gap detection
- Assumption fragility scoring
- Bridge weakness checking (for cross-domain candidates)

Follows the same deterministic, explainable pattern as harnesses.py.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from .models import CandidateHypothesis, EvidencePack, new_id

logger = logging.getLogger(__name__)

# Negation/contradiction words to look for in evidence vs mechanism
NEGATION_PHRASES = [
    "does not", "do not", "did not", "cannot", "can not", "could not",
    "fails to", "failed to", "unable to", "no evidence", "no support",
    "contradicts", "contrary to", "in contrast", "however", "but",
    "limits", "limited by", "problems with", "issues with",
    "ineffective", "unstable", "degraded", "degradation",
]

# Phrases indicating fragile assumptions
FRAGILE_ASSUMPTION_PHRASES = [
    "assumed", "assuming", "if this holds", "under ideal",
    "in theory", "theoretically", "speculative", "unclear",
    "unknown", "not yet", "remains to be", "further work",
]

# Phrases indicating robust assumptions
ROBUST_ASSUMPTION_PHRASES = [
    "demonstrated", "confirmed", "validated", "proven",
    "established", "well-known", "widely accepted",
    "experimentally shown", "measured",
]

# Bridge-related weakness indicators
BRIDGE_WEAKNESS_INDICATORS = [
    "speculative bridge", "unclear connection", "tenuous link",
    "superficial", "vague mechanism", "no direct link",
]

# Minimum evidence items expected for a credible candidate
MIN_EVIDENCE_FOR_PASS = 2


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tokenize(text: str) -> set:
    """Simple word tokenizer for overlap detection."""
    words = re.findall(r'\b[a-z]{3,}\b', text.lower())
    stopwords = {"the", "and", "that", "with", "this", "from", "are",
                 "for", "has", "have", "was", "were", "been", "its",
                 "not", "but", "can", "may", "will", "also", "more"}
    return {w for w in words if w not in stopwords}


def _similarity(a: str, b: str) -> float:
    """String similarity via SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# FalsificationSummary
# ---------------------------------------------------------------------------

@dataclass
class FalsificationSummary:
    """Result of falsification analysis for one candidate."""
    id: str = ""
    candidate_id: str = ""
    run_id: str = ""

    contradictions_found: list = field(default_factory=list)
    missing_evidence_gaps: list = field(default_factory=list)
    assumption_fragility_score: float = 0.5   # 0=fragile, 1=robust
    bridge_weakness_flags: list = field(default_factory=list)

    overall_falsification_risk: str = "medium"  # "low" | "medium" | "high"
    falsification_passed: bool = True
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "contradictions_found": self.contradictions_found,
            "missing_evidence_gaps": self.missing_evidence_gaps,
            "assumption_fragility_score": round(self.assumption_fragility_score, 3),
            "bridge_weakness_flags": self.bridge_weakness_flags,
            "overall_falsification_risk": self.overall_falsification_risk,
            "falsification_passed": self.falsification_passed,
            "reasoning": self.reasoning,
        }

    def format(self) -> str:
        lines = [
            f"Falsification Risk: {self.overall_falsification_risk.upper()}",
            f"Passed: {self.falsification_passed}",
            f"Assumption fragility: {self.assumption_fragility_score:.2f} "
            f"({'robust' if self.assumption_fragility_score >= 0.6 else 'fragile'})",
        ]
        if self.contradictions_found:
            lines.append(f"Contradictions ({len(self.contradictions_found)}):")
            for c in self.contradictions_found:
                lines.append(f"  - {c}")
        if self.missing_evidence_gaps:
            lines.append(f"Missing evidence ({len(self.missing_evidence_gaps)}):")
            for g in self.missing_evidence_gaps:
                lines.append(f"  - {g}")
        if self.bridge_weakness_flags:
            lines.append(f"Bridge weakness ({len(self.bridge_weakness_flags)}):")
            for b in self.bridge_weakness_flags:
                lines.append(f"  - {b}")
        if self.reasoning:
            lines.append(f"Reasoning: {self.reasoning}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# FalsificationEngine
# ---------------------------------------------------------------------------

class FalsificationEngine:
    """Rule-based falsification analysis. No LLM calls."""

    def evaluate(
        self,
        candidate: CandidateHypothesis,
        evidence_pack: Optional[EvidencePack],
        synthesis_context=None,
    ) -> FalsificationSummary:
        """Run full falsification analysis on a candidate."""
        fid = new_id()

        contradictions = self.check_contradictions(candidate, evidence_pack)
        missing = self.check_missing_evidence(candidate, evidence_pack)
        fragility = self.assess_assumption_fragility(candidate)
        bridge_weakness = self.check_bridge_weakness(candidate, synthesis_context)

        # Compute overall risk
        risk, passed, reasoning = self._compute_risk(
            contradictions, missing, fragility, bridge_weakness
        )

        summary = FalsificationSummary(
            id=fid,
            candidate_id=candidate.id,
            run_id=candidate.run_id,
            contradictions_found=contradictions,
            missing_evidence_gaps=missing,
            assumption_fragility_score=fragility,
            bridge_weakness_flags=bridge_weakness,
            overall_falsification_risk=risk,
            falsification_passed=passed,
            reasoning=reasoning,
        )
        return summary

    def check_contradictions(
        self,
        candidate: CandidateHypothesis,
        evidence_pack: Optional[EvidencePack],
    ) -> list:
        """Detect evidence quotes that may contradict the mechanism.

        A contradiction is flagged when:
        1. An evidence quote contains a negation phrase AND
        2. The quote shares meaningful keyword overlap with the mechanism.
        """
        if evidence_pack is None or not evidence_pack.items:
            return []

        mechanism_tokens = _tokenize(candidate.mechanism)
        contradictions = []

        for item in evidence_pack.items:
            quote_lower = item.quote.lower()
            quote_tokens = _tokenize(item.quote)

            # Check overlap between quote and mechanism
            overlap = mechanism_tokens & quote_tokens
            if len(overlap) < 2:
                continue  # Not related enough to be a contradiction

            # Look for negation phrases in the quote
            for phrase in NEGATION_PHRASES:
                if phrase in quote_lower:
                    excerpt = item.quote[:120].strip()
                    contradictions.append(
                        f"Evidence from '{item.title[:50]}' contains '{phrase}' "
                        f"with mechanism overlap {sorted(overlap)[:3]}: \"{excerpt}...\""
                    )
                    break  # One flag per evidence item

        return contradictions

    def check_missing_evidence(
        self,
        candidate: CandidateHypothesis,
        evidence_pack: Optional[EvidencePack],
        min_items: int = MIN_EVIDENCE_FOR_PASS,
    ) -> list:
        """Flag evidence gaps in coverage."""
        gaps = []

        if evidence_pack is None or len(evidence_pack.items) == 0:
            gaps.append("No evidence attached to candidate")
            return gaps

        n = len(evidence_pack.items)
        if n < min_items:
            gaps.append(f"Insufficient evidence: {n} item(s), minimum {min_items} required")

        # Check that at least one evidence item is relevant to the mechanism
        mechanism_tokens = _tokenize(candidate.mechanism)
        max_overlap = 0
        for item in evidence_pack.items:
            quote_tokens = _tokenize(item.quote)
            overlap = len(mechanism_tokens & quote_tokens)
            max_overlap = max(max_overlap, overlap)

        if max_overlap < 2:
            gaps.append(
                "No evidence item has meaningful keyword overlap with the mechanism "
                f"(max overlap: {max_overlap} words)"
            )

        # For cross-domain candidates: check for both domain coverage
        if candidate.domain and "+" in candidate.domain:
            parts = candidate.domain.split("+")
            domain_a, domain_b = parts[0].strip(), parts[1].strip()
            titles_lower = " ".join(item.title.lower() for item in evidence_pack.items)
            quotes_lower = " ".join(item.quote.lower() for item in evidence_pack.items)
            text = titles_lower + " " + quotes_lower

            a_tokens = _tokenize(domain_a.replace("-", " "))
            b_tokens = _tokenize(domain_b.replace("-", " "))
            a_coverage = any(t in text for t in a_tokens)
            b_coverage = any(t in text for t in b_tokens)

            if not a_coverage:
                gaps.append(f"No evidence covering primary domain: '{domain_a}'")
            if not b_coverage:
                gaps.append(f"No evidence covering secondary domain: '{domain_b}'")

        return gaps

    def assess_assumption_fragility(self, candidate: CandidateHypothesis) -> float:
        """Score assumption robustness.

        Returns 0.0 (fragile) to 1.0 (robust).
        """
        if not candidate.assumptions:
            return 0.4  # No assumptions stated — slightly fragile

        assumptions_text = " ".join(
            a if isinstance(a, str) else str(a)
            for a in candidate.assumptions
        ).lower()

        fragile_count = sum(
            1 for phrase in FRAGILE_ASSUMPTION_PHRASES
            if phrase in assumptions_text
        )
        robust_count = sum(
            1 for phrase in ROBUST_ASSUMPTION_PHRASES
            if phrase in assumptions_text
        )
        n_assumptions = max(len(candidate.assumptions), 1)

        # Base score: more assumptions (up to 3) slightly increases robustness
        # because explicitly stated is better than hidden
        base = min(0.5 + 0.1 * min(n_assumptions, 3), 0.7)

        # Penalize fragile language
        fragile_penalty = min(fragile_count * 0.15, 0.4)

        # Reward robust language
        robust_bonus = min(robust_count * 0.1, 0.3)

        score = max(0.0, min(1.0, base - fragile_penalty + robust_bonus))
        return score

    def check_bridge_weakness(
        self,
        candidate: CandidateHypothesis,
        synthesis_context=None,
    ) -> list:
        """Flag weak cross-domain bridges.

        For non-cross-domain candidates, returns an empty list.
        """
        flags = []

        # Only meaningful for cross-domain candidates
        if not candidate.domain or "+" not in candidate.domain:
            return flags

        mechanism_lower = candidate.mechanism.lower()
        statement_lower = candidate.statement.lower()
        combined = mechanism_lower + " " + statement_lower

        # Check for generic bridge weakness indicators
        for indicator in BRIDGE_WEAKNESS_INDICATORS:
            if indicator in combined:
                flags.append(f"Bridge weakness indicator found: '{indicator}'")

        # Check mechanism length as proxy for depth (short = superficial)
        if len(candidate.mechanism.strip()) < 80:
            flags.append(
                f"Mechanism may be too shallow for cross-domain synthesis "
                f"(length: {len(candidate.mechanism.strip())} chars)"
            )

        # Reuse SynthesisFitEvaluator logic if synthesis context is available
        if synthesis_context is not None:
            from .synthesis import SynthesisFitEvaluator
            evaluator = SynthesisFitEvaluator()
            # We need an evidence pack for full evaluation — skip if unavailable
            # Just check bridge score from mechanism keywords
            try:
                bridge_mech = getattr(synthesis_context, "bridge_mechanism", "")
                if bridge_mech:
                    bridge_tokens = _tokenize(bridge_mech)
                    mechanism_tokens = _tokenize(candidate.mechanism)
                    overlap = len(bridge_tokens & mechanism_tokens)
                    if overlap < 2:
                        flags.append(
                            f"Mechanism has low overlap with expected bridge "
                            f"'{bridge_mech}' (overlap: {overlap} words)"
                        )
            except Exception as e:
                logger.debug("Bridge weakness check partial failure: %s", e)

        return flags

    def _compute_risk(
        self,
        contradictions: list,
        missing: list,
        fragility: float,
        bridge_weakness: list,
    ) -> tuple:
        """Compute overall risk level, pass/fail, and reasoning."""
        issues = []

        if contradictions:
            issues.append(f"{len(contradictions)} contradiction(s)")
        if missing:
            critical_missing = [m for m in missing if "No evidence" in m or "Insufficient" in m]
            if critical_missing:
                issues.append(f"{len(critical_missing)} critical evidence gap(s)")
        if fragility < 0.3:
            issues.append(f"highly fragile assumptions (score={fragility:.2f})")
        if len(bridge_weakness) >= 2:
            issues.append(f"{len(bridge_weakness)} bridge weakness flag(s)")

        n_issues = len(issues)

        if n_issues == 0 and fragility >= 0.5:
            risk = "low"
            passed = True
            reasoning = "No significant falsification risks identified."
        elif n_issues <= 1 and fragility >= 0.3:
            risk = "medium"
            passed = True
            reasoning = f"Minor concerns: {'; '.join(issues) or 'none'}. Reviewable."
        else:
            risk = "high"
            passed = False
            reasoning = f"Significant concerns: {'; '.join(issues)}. Recommend rejection or major revision."

        return risk, passed, reasoning

    def save_summary(self, repo, summary: FalsificationSummary) -> None:
        """Persist falsification summary to bt_falsification_summaries."""
        import json
        repo.db.execute(
            """INSERT OR REPLACE INTO bt_falsification_summaries
               (id, candidate_id, run_id, contradictions_json, missing_evidence_json,
                assumption_fragility_score, bridge_weakness_json, falsification_risk,
                passed, reasoning)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                summary.id,
                summary.candidate_id,
                summary.run_id,
                json.dumps(summary.contradictions_found),
                json.dumps(summary.missing_evidence_gaps),
                summary.assumption_fragility_score,
                json.dumps(summary.bridge_weakness_flags),
                summary.overall_falsification_risk,
                int(summary.falsification_passed),
                summary.reasoning,
            ),
        )
        repo.db.commit()

    def load_summary(self, repo, candidate_id: str) -> Optional[FalsificationSummary]:
        """Load a saved falsification summary."""
        import json
        row = repo.db.execute(
            "SELECT * FROM bt_falsification_summaries WHERE candidate_id=? ORDER BY created_at DESC LIMIT 1",
            (candidate_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        return FalsificationSummary(
            id=d["id"],
            candidate_id=d["candidate_id"],
            run_id=d["run_id"],
            contradictions_found=json.loads(d.get("contradictions_json") or "[]"),
            missing_evidence_gaps=json.loads(d.get("missing_evidence_json") or "[]"),
            assumption_fragility_score=d.get("assumption_fragility_score", 0.5),
            bridge_weakness_flags=json.loads(d.get("bridge_weakness_json") or "[]"),
            overall_falsification_risk=d.get("falsification_risk", "medium"),
            falsification_passed=bool(d.get("passed", 1)),
            reasoning=d.get("reasoning", ""),
        )
