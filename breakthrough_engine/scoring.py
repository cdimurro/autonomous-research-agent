"""Candidate scoring logic with explicit formula and tie-breaking.

v1 uses weighted sum scoring. Structure supports future Bayesian updating.
"""

from __future__ import annotations

from .models import (
    CandidateHypothesis,
    CandidateScore,
    EvidencePack,
    HarnessDecision,
    ResearchProgram,
    SimulationResult,
    SimulationStatus,
)


def score_candidate(
    candidate: CandidateHypothesis,
    evidence_pack: EvidencePack | None,
    simulation_result: SimulationResult | None,
    harness_decisions: list[HarnessDecision],
    program: ResearchProgram,
) -> CandidateScore:
    """Compute a multi-dimensional score for a candidate.

    Individual dimension scores are computed from available data.
    Final score uses the program's weighted formula.
    """
    score = CandidateScore(candidate_id=candidate.id)

    # Novelty: based on novelty_notes length and absence of duplication
    novelty_text = candidate.novelty_notes.strip()
    if novelty_text:
        score.novelty_score = min(1.0, len(novelty_text) / 200.0)
    else:
        score.novelty_score = 0.3  # baseline for having a hypothesis at all

    # Plausibility: based on mechanism detail and absence of risk flags
    mechanism_len = len(candidate.mechanism.strip())
    score.plausibility_score = min(1.0, mechanism_len / 150.0)
    if candidate.risk_flags:
        score.plausibility_score *= max(0.3, 1.0 - 0.15 * len(candidate.risk_flags))

    # Impact: based on expected outcome detail
    outcome_len = len(candidate.expected_outcome.strip())
    score.impact_score = min(1.0, outcome_len / 150.0)

    # Evidence strength: from evidence pack
    if evidence_pack and evidence_pack.items:
        avg_relevance = sum(i.relevance_score for i in evidence_pack.items) / len(
            evidence_pack.items
        )
        diversity_bonus = min(0.2, evidence_pack.source_diversity_count * 0.05)
        score.evidence_strength_score = min(1.0, avg_relevance + diversity_bonus)
    else:
        score.evidence_strength_score = 0.1

    # Simulation readiness
    if simulation_result and simulation_result.status == SimulationStatus.COMPLETED:
        score.simulation_readiness_score = 0.9
        # Boost if metrics are positive
        if simulation_result.key_metrics.get("success", False):
            score.simulation_readiness_score = 1.0
    elif simulation_result and simulation_result.status == SimulationStatus.SKIPPED:
        score.simulation_readiness_score = 0.3
    else:
        score.simulation_readiness_score = 0.2

    # Validation cost: lower is better (inverted in final formula)
    hours = candidate.testability_window_hours
    if hours <= 1:
        score.validation_cost_score = 0.1  # very cheap
    elif hours <= 24:
        score.validation_cost_score = 0.3
    elif hours <= 168:  # 1 week
        score.validation_cost_score = 0.5
    elif hours <= 720:  # 1 month
        score.validation_cost_score = 0.7
    else:
        score.validation_cost_score = 0.9

    # Harness bonus: passed harnesses contribute a small boost
    harness_pass_count = sum(1 for h in harness_decisions if h.passed)
    if harness_decisions:
        harness_ratio = harness_pass_count / len(harness_decisions)
        # Small adjustment: up to +0.05 for all harnesses passing
        for attr in ["novelty_score", "plausibility_score"]:
            current = getattr(score, attr)
            setattr(score, attr, min(1.0, current + 0.05 * harness_ratio))

    score.compute_final(program.scoring_weights)
    return score


def rank_candidates(
    scores: list[CandidateScore],
    publication_gate_passed: dict[str, bool] | None = None,
) -> list[CandidateScore]:
    """Rank candidates by final score with tie-breaking.

    Tie-break order:
    1. Publication gate pass (passed > not passed)
    2. Higher evidence_strength
    3. Lower validation_cost
    4. Earlier candidate_id (deterministic fallback)
    """
    gate = publication_gate_passed or {}

    def sort_key(s: CandidateScore):
        return (
            -(1 if gate.get(s.candidate_id, False) else 0),  # gate pass first
            -s.final_score,
            -s.evidence_strength_score,
            s.validation_cost_score,  # lower cost wins
            s.candidate_id,  # deterministic fallback
        )

    return sorted(scores, key=sort_key)
