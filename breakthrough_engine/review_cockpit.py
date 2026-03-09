"""Review cockpit for Breakthrough Engine Phase 6.

Produces structured ReviewDecisionPackets that consolidate all relevant
signals for a candidate, reducing operator review burden.

The cockpit:
- Summarizes the candidate
- Explains why it beat challengers (if campaign context available)
- Shows posterior confidence (if Bayesian tracking active)
- Shows falsification risk
- Shows evidence balance and novelty neighbors
- Shows synthesis fit summary
- Recommends APPROVE / DEFER / REJECT with explicit rationale
- Renders as plain text (CLI) or minimal HTML (Flask API)

No JavaScript framework. No SPA. Server-rendered only.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .models import CandidateHypothesis, EvidencePack, new_id

logger = logging.getLogger(__name__)

# Thresholds for recommended action
APPROVE_THRESHOLD = 0.75
DEFER_THRESHOLD = 0.60


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_str(v) -> str:
    """Convert any value to a safe displayable string."""
    if v is None:
        return "N/A"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


# ---------------------------------------------------------------------------
# ReviewDecisionPacket
# ---------------------------------------------------------------------------

@dataclass
class ReviewDecisionPacket:
    """Complete review packet for one candidate."""
    candidate_id: str
    run_id: str
    campaign_id: str = ""

    candidate_summary: str = ""
    why_beat_challengers: str = ""

    # Bayesian confidence (optional — not all runs have Bayesian tracking)
    posterior_confidence: Optional[dict] = None   # PosteriorSummary.to_dict() or None

    # Falsification (optional — not all runs have falsification)
    falsification_summary: Optional[dict] = None  # FalsificationSummary.to_dict() or None

    evidence_balance_summary: str = ""
    novelty_neighbor_summary: str = ""
    synthesis_fit_summary: str = ""

    recommended_action: str = "DEFER"   # "APPROVE" | "DEFER" | "REJECT"
    recommendation_rationale: str = ""

    runner_up_comparison: Optional[dict] = None

    # Scoring context
    final_score: float = 0.0
    candidate_title: str = ""
    candidate_domain: str = ""

    id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "campaign_id": self.campaign_id,
            "candidate_title": self.candidate_title,
            "candidate_domain": self.candidate_domain,
            "candidate_summary": self.candidate_summary,
            "why_beat_challengers": self.why_beat_challengers,
            "posterior_confidence": self.posterior_confidence,
            "falsification_summary": self.falsification_summary,
            "evidence_balance_summary": self.evidence_balance_summary,
            "novelty_neighbor_summary": self.novelty_neighbor_summary,
            "synthesis_fit_summary": self.synthesis_fit_summary,
            "recommended_action": self.recommended_action,
            "recommendation_rationale": self.recommendation_rationale,
            "runner_up_comparison": self.runner_up_comparison,
            "final_score": round(self.final_score, 4),
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# ReviewCockpit
# ---------------------------------------------------------------------------

class ReviewCockpit:
    """Builds and formats ReviewDecisionPackets."""

    def build_packet(
        self,
        candidate: CandidateHypothesis,
        evidence_pack: Optional[EvidencePack],
        synthesis_fit=None,         # SynthesisFitResult or dict or None
        novelty_result=None,        # NoveltyResult or dict or None
        candidate_score=None,       # CandidateScore or dict or None
        posterior_summary=None,     # PosteriorSummary or dict or None
        falsification_summary=None, # FalsificationSummary or dict or None
        runner_ups: Optional[list] = None,  # list of (CandidateHypothesis, score)
        campaign_id: str = "",
    ) -> ReviewDecisionPacket:
        """Build a full review decision packet for a candidate."""
        # Extract final score
        final_score = 0.0
        if candidate_score is not None:
            if hasattr(candidate_score, "final_score"):
                final_score = candidate_score.final_score
            elif isinstance(candidate_score, dict):
                final_score = float(candidate_score.get("final_score", 0.0))

        # Build candidate summary
        summary = self._build_candidate_summary(candidate)

        # Build evidence balance summary
        evidence_summary = self._build_evidence_summary(candidate, evidence_pack, synthesis_fit)

        # Build novelty neighbor summary
        novelty_summary = self._build_novelty_summary(novelty_result)

        # Build synthesis fit summary
        synth_summary = self._build_synthesis_summary(synthesis_fit)

        # Build challenger comparison
        challenger_summary = self._build_challenger_summary(candidate, final_score, runner_ups)

        # Determine recommended action
        action, rationale = self._determine_action(
            final_score=final_score,
            falsification_summary=falsification_summary,
        )

        # Convert Bayesian summary to dict if needed
        posterior_dict = None
        if posterior_summary is not None:
            if hasattr(posterior_summary, "to_dict"):
                posterior_dict = posterior_summary.to_dict()
            elif isinstance(posterior_summary, dict):
                posterior_dict = posterior_summary

        # Convert falsification summary to dict if needed
        falsification_dict = None
        if falsification_summary is not None:
            if hasattr(falsification_summary, "to_dict"):
                falsification_dict = falsification_summary.to_dict()
            elif isinstance(falsification_summary, dict):
                falsification_dict = falsification_summary

        # Runner-up comparison
        runner_up_dict = None
        if runner_ups:
            runner_up_dict = self._build_runner_up_dict(candidate, final_score, runner_ups)

        return ReviewDecisionPacket(
            id=new_id(),
            candidate_id=candidate.id,
            run_id=candidate.run_id,
            campaign_id=campaign_id,
            candidate_title=candidate.title,
            candidate_domain=candidate.domain,
            candidate_summary=summary,
            why_beat_challengers=challenger_summary,
            posterior_confidence=posterior_dict,
            falsification_summary=falsification_dict,
            evidence_balance_summary=evidence_summary,
            novelty_neighbor_summary=novelty_summary,
            synthesis_fit_summary=synth_summary,
            recommended_action=action,
            recommendation_rationale=rationale,
            runner_up_comparison=runner_up_dict,
            final_score=final_score,
            created_at=_utcnow(),
        )

    def format_as_text(self, packet: ReviewDecisionPacket) -> str:
        """Format a review packet as plain text for CLI display."""
        border = "═" * 65
        thin = "─" * 65
        lines = [
            border,
            "REVIEW DECISION PACKET",
            border,
            f"Candidate:  {packet.candidate_title}",
            f"Domain:     {packet.candidate_domain}",
            f"Candidate ID: {packet.candidate_id}",
            f"Run ID:     {packet.run_id}",
            "",
        ]

        # Candidate summary
        lines += [
            "SUMMARY",
            thin,
            packet.candidate_summary or "(no summary)",
            "",
        ]

        # Scores
        lines += [
            "SCORES",
            thin,
            f"  Final Score:    {packet.final_score:.3f}",
        ]

        # Falsification
        if packet.falsification_summary:
            fs = packet.falsification_summary
            risk = fs.get("overall_falsification_risk", "unknown").upper()
            passed = "YES" if fs.get("falsification_passed", True) else "NO"
            fragility = fs.get("assumption_fragility_score", 0.5)
            lines += [
                "",
                f"FALSIFICATION RISK: {risk}",
                thin,
                f"  Passed:         {passed}",
                f"  Assumption fragility: {fragility:.2f} "
                f"({'robust' if fragility >= 0.6 else 'fragile'})",
            ]
            if fs.get("contradictions_found"):
                lines.append(f"  Contradictions: {len(fs['contradictions_found'])}")
            if fs.get("missing_evidence_gaps"):
                lines.append(f"  Evidence gaps:  {len(fs['missing_evidence_gaps'])}")
            if fs.get("bridge_weakness_flags"):
                lines.append(f"  Bridge flags:   {len(fs['bridge_weakness_flags'])}")
        else:
            lines += ["", "FALSIFICATION: Not evaluated", thin]

        # Bayesian posterior
        if packet.posterior_confidence:
            ps = packet.posterior_confidence
            lines += [
                "",
                "POSTERIOR CONFIDENCE",
                thin,
                f"  Metric:       {ps.get('metric_name', 'N/A')}",
                f"  Mean:         {ps.get('mean', 0):.3f}",
                f"  95% CI:       [{ps.get('ci_lower', 0):.3f}, {ps.get('ci_upper', 0):.3f}]",
                f"  Sample size:  {ps.get('sample_size', 0)} ({ps.get('uncertainty_label', 'unknown')} uncertainty)",
            ]

        # Evidence balance
        if packet.evidence_balance_summary:
            lines += ["", "EVIDENCE BALANCE", thin, packet.evidence_balance_summary]

        # Novelty neighbors
        if packet.novelty_neighbor_summary:
            lines += ["", "NOVELTY NEIGHBORS", thin, packet.novelty_neighbor_summary]

        # Synthesis fit
        if packet.synthesis_fit_summary:
            lines += ["", "SYNTHESIS FIT", thin, packet.synthesis_fit_summary]

        # Why beat challengers
        if packet.why_beat_challengers and packet.why_beat_challengers != "N/A":
            lines += ["", "WHY THIS CANDIDATE WON", thin, packet.why_beat_challengers]

        # Runner-up comparison
        if packet.runner_up_comparison:
            lines += ["", "RUNNER-UP COMPARISON", thin]
            for entry in packet.runner_up_comparison.get("runner_ups", []):
                lines.append(
                    f"  {entry.get('title', '?')[:50]}: score={entry.get('score', 0):.3f}"
                )

        # Recommendation
        lines += [
            "",
            border,
            f"RECOMMENDED ACTION: {packet.recommended_action}",
            f"Rationale: {packet.recommendation_rationale}",
            border,
        ]
        return "\n".join(lines)

    def format_as_html(self, packet: ReviewDecisionPacket) -> str:
        """Minimal server-rendered HTML for the Flask cockpit endpoint."""
        action_class = {
            "APPROVE": "action-approve",
            "DEFER": "action-defer",
            "REJECT": "action-reject",
        }.get(packet.recommended_action, "action-defer")

        def esc(s):
            return (str(s)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

        rows = []
        rows.append(f"<tr><th>Final Score</th><td>{packet.final_score:.3f}</td></tr>")

        if packet.falsification_summary:
            fs = packet.falsification_summary
            risk = fs.get("overall_falsification_risk", "unknown")
            rows.append(f"<tr><th>Falsification Risk</th><td>{esc(risk.upper())}</td></tr>")
            rows.append(f"<tr><th>Assumption Fragility</th><td>{fs.get('assumption_fragility_score', 0):.2f}</td></tr>")

        if packet.posterior_confidence:
            ps = packet.posterior_confidence
            rows.append(
                f"<tr><th>Posterior ({esc(ps.get('metric_name',''))})</th>"
                f"<td>mean={ps.get('mean',0):.3f}, n={ps.get('sample_size',0)} "
                f"({esc(ps.get('uncertainty_label',''))})</td></tr>"
            )

        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Review Cockpit — {esc(packet.candidate_title)}</title>
  <style>
    body {{ font-family: monospace; max-width: 900px; margin: 2em auto; padding: 0 1em; }}
    h1 {{ font-size: 1.2em; border-bottom: 2px solid #333; }}
    h2 {{ font-size: 1em; color: #555; margin-top: 1.5em; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th {{ text-align: left; padding: 4px 8px; background: #f4f4f4; width: 35%; }}
    td {{ padding: 4px 8px; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    pre {{ background: #f8f8f8; padding: 1em; overflow-x: auto; font-size: 0.9em; }}
    .action-approve {{ background: #d4edda; padding: 1em; border-left: 4px solid #28a745; }}
    .action-defer {{ background: #fff3cd; padding: 1em; border-left: 4px solid #ffc107; }}
    .action-reject {{ background: #f8d7da; padding: 1em; border-left: 4px solid #dc3545; }}
  </style>
</head>
<body>
<h1>Review Decision Packet</h1>
<p><strong>{esc(packet.candidate_title)}</strong><br>
   Domain: {esc(packet.candidate_domain)} | ID: {esc(packet.candidate_id)}</p>

<h2>Summary</h2>
<p>{esc(packet.candidate_summary)}</p>

<h2>Signals</h2>
<table>
  {''.join(rows)}
</table>

<h2>Evidence Balance</h2>
<pre>{esc(packet.evidence_balance_summary or "(not available)")}</pre>

<h2>Synthesis Fit</h2>
<pre>{esc(packet.synthesis_fit_summary or "(not available)")}</pre>

<h2>Novelty</h2>
<pre>{esc(packet.novelty_neighbor_summary or "(not available)")}</pre>

<div class="{action_class}">
  <strong>Recommended Action: {esc(packet.recommended_action)}</strong><br>
  {esc(packet.recommendation_rationale)}
</div>

<p style="color:#999; font-size:0.8em; margin-top:2em;">Generated {esc(packet.created_at)}</p>
</body>
</html>"""
        return html

    def save_packet(self, repo, packet: ReviewDecisionPacket) -> None:
        """Persist a review packet to the database (optional)."""
        # Stored in bt_falsification_summaries if falsification was run;
        # full packet stored as JSON in bt_baseline_comparisons for now.
        # For full persistence, callers can serialize packet.to_dict() as needed.
        pass

    # ---------------------
    # Private helpers
    # ---------------------

    def _build_candidate_summary(self, candidate: CandidateHypothesis) -> str:
        """One-paragraph summary of the candidate."""
        summary = candidate.statement
        if candidate.mechanism:
            summary += f" The proposed mechanism: {candidate.mechanism[:200]}"
        if candidate.expected_outcome:
            summary += f" Expected outcome: {candidate.expected_outcome[:150]}"
        return summary

    def _build_evidence_summary(self, candidate, evidence_pack, synthesis_fit) -> str:
        """Evidence balance summary."""
        if evidence_pack is None or not evidence_pack.items:
            return "No evidence attached."

        n = len(evidence_pack.items)
        avg_relevance = sum(i.relevance_score for i in evidence_pack.items) / n
        source_types = set(i.source_type for i in evidence_pack.items)

        summary = (
            f"{n} evidence item(s), avg relevance={avg_relevance:.2f}, "
            f"sources: {', '.join(sorted(source_types))}"
        )

        if synthesis_fit is not None:
            eb = None
            if hasattr(synthesis_fit, "evidence_balance_score"):
                eb = synthesis_fit.evidence_balance_score
            elif isinstance(synthesis_fit, dict):
                eb = synthesis_fit.get("evidence_balance_score")
            if eb is not None:
                summary += f"\nEvidence balance (primary/secondary): {eb:.2f}"

        return summary

    def _build_novelty_summary(self, novelty_result) -> str:
        """Novelty neighbor summary."""
        if novelty_result is None:
            return "Novelty not evaluated."

        decision = ""
        explanation = ""
        neighbors = []

        if hasattr(novelty_result, "decision"):
            decision = getattr(novelty_result.decision, "value", str(novelty_result.decision))
            explanation = getattr(novelty_result, "explanation", "")
        elif isinstance(novelty_result, dict):
            decision = novelty_result.get("decision", "")
            explanation = novelty_result.get("explanation", "")

        summary = f"Decision: {decision.upper()}"
        if explanation:
            summary += f"\n{explanation[:200]}"
        return summary

    def _build_synthesis_summary(self, synthesis_fit) -> str:
        """Synthesis fit summary."""
        if synthesis_fit is None:
            return "Synthesis fit not evaluated (single-domain run)."

        score = None
        bridge_score = None
        balance = None
        passed = None

        if hasattr(synthesis_fit, "cross_domain_fit_score"):
            score = synthesis_fit.cross_domain_fit_score
            bridge_score = getattr(synthesis_fit, "bridge_mechanism_score", None)
            balance = getattr(synthesis_fit, "evidence_balance_score", None)
            passed = getattr(synthesis_fit, "passed", None)
        elif isinstance(synthesis_fit, dict):
            score = synthesis_fit.get("cross_domain_fit_score")
            bridge_score = synthesis_fit.get("bridge_mechanism_score")
            balance = synthesis_fit.get("evidence_balance_score")
            passed = synthesis_fit.get("passed")

        parts = []
        if score is not None:
            parts.append(f"Cross-domain fit: {score:.3f}")
        if bridge_score is not None:
            parts.append(f"Bridge strength: {bridge_score:.3f}")
        if balance is not None:
            parts.append(f"Evidence balance: {balance:.3f}")
        if passed is not None:
            parts.append(f"Passed: {bool(passed)}")
        return "\n".join(parts) if parts else "No synthesis data available."

    def _build_challenger_summary(
        self,
        candidate: CandidateHypothesis,
        final_score: float,
        runner_ups: Optional[list],
    ) -> str:
        """Explain why this candidate beat its challengers."""
        if not runner_ups:
            return "N/A — single candidate in this run."

        lines = [f"Selected with score {final_score:.3f} over {len(runner_ups)} alternative(s):"]
        for i, (alt_candidate, alt_score) in enumerate(runner_ups[:3], 1):
            title = getattr(alt_candidate, "title", str(alt_candidate))
            delta = final_score - alt_score
            lines.append(f"  {i}. {title[:50]}: score={alt_score:.3f} (Δ={delta:+.3f})")
        return "\n".join(lines)

    def _build_runner_up_dict(
        self,
        champion: CandidateHypothesis,
        champion_score: float,
        runner_ups: list,
    ) -> dict:
        """Build structured runner-up comparison dict."""
        return {
            "champion": {
                "id": champion.id,
                "title": champion.title,
                "score": round(champion_score, 4),
            },
            "runner_ups": [
                {
                    "id": getattr(c, "id", ""),
                    "title": getattr(c, "title", str(c))[:80],
                    "score": round(s, 4),
                }
                for c, s in runner_ups[:5]
            ],
        }

    def _determine_action(
        self,
        final_score: float,
        falsification_summary=None,
    ) -> tuple:
        """Determine APPROVE / DEFER / REJECT with rationale."""
        falsification_passed = True
        falsification_risk = "unknown"

        if falsification_summary is not None:
            if hasattr(falsification_summary, "falsification_passed"):
                falsification_passed = falsification_summary.falsification_passed
                falsification_risk = getattr(
                    falsification_summary, "overall_falsification_risk", "unknown"
                )
            elif isinstance(falsification_summary, dict):
                falsification_passed = falsification_summary.get("falsification_passed", True)
                falsification_risk = falsification_summary.get("overall_falsification_risk", "unknown")

        if final_score >= APPROVE_THRESHOLD and falsification_passed:
            action = "APPROVE"
            rationale = (
                f"Score {final_score:.3f} >= {APPROVE_THRESHOLD} "
                f"and falsification risk {falsification_risk} (passed)."
            )
        elif final_score >= DEFER_THRESHOLD:
            action = "DEFER"
            if not falsification_passed:
                rationale = (
                    f"Score {final_score:.3f} >= {DEFER_THRESHOLD} but "
                    f"falsification risk is {falsification_risk}. Manual review recommended."
                )
            else:
                rationale = (
                    f"Score {final_score:.3f} is review-worthy but below approve threshold "
                    f"({APPROVE_THRESHOLD}). Defer for manual review."
                )
        else:
            action = "REJECT"
            rationale = (
                f"Score {final_score:.3f} < {DEFER_THRESHOLD} "
                f"(minimum review-worthiness threshold)."
            )

        return action, rationale
