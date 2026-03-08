"""Tests for scoring module."""

from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    EvidenceItem,
    EvidencePack,
    HarnessDecision,
    ResearchProgram,
    SimulationResult,
    SimulationStatus,
)
from breakthrough_engine.scoring import rank_candidates, score_candidate


def _make_program():
    return ResearchProgram(name="test", domain="test")


def _make_candidate(**kw):
    defaults = dict(
        title="Test", domain="test",
        statement="A detailed hypothesis statement for testing purposes",
        mechanism="A detailed mechanism explaining the causal pathway involved",
        expected_outcome="A measurable outcome within standard laboratory conditions",
        assumptions=["Assumption 1"],
        novelty_notes="This is a novel approach combining two previously unrelated fields.",
    )
    defaults.update(kw)
    return CandidateHypothesis(**defaults)


def test_score_candidate_basic():
    c = _make_candidate()
    pack = EvidencePack(
        candidate_id=c.id,
        items=[
            EvidenceItem(source_type="paper", source_id="s1", title="T",
                         quote="Q", citation="C", relevance_score=0.8),
            EvidenceItem(source_type="paper", source_id="s2", title="T2",
                         quote="Q2", citation="C2", relevance_score=0.7),
        ],
        source_diversity_count=2,
    )
    sim = SimulationResult(
        candidate_id=c.id, status=SimulationStatus.COMPLETED,
        key_metrics={"success": True},
    )
    score = score_candidate(c, pack, sim, [], _make_program())
    assert 0.0 < score.final_score <= 1.0
    assert score.simulation_readiness_score == 1.0


def test_score_without_simulation():
    c = _make_candidate()
    score = score_candidate(c, None, None, [], _make_program())
    assert score.final_score > 0
    assert score.simulation_readiness_score < 0.5


def test_rank_candidates_by_score():
    scores = [
        CandidateScore(candidate_id="c1", final_score=0.5),
        CandidateScore(candidate_id="c2", final_score=0.8),
        CandidateScore(candidate_id="c3", final_score=0.6),
    ]
    ranked = rank_candidates(scores)
    assert ranked[0].candidate_id == "c2"
    assert ranked[1].candidate_id == "c3"
    assert ranked[2].candidate_id == "c1"


def test_rank_tiebreak_evidence_strength():
    scores = [
        CandidateScore(candidate_id="c1", final_score=0.7, evidence_strength_score=0.5),
        CandidateScore(candidate_id="c2", final_score=0.7, evidence_strength_score=0.9),
    ]
    ranked = rank_candidates(scores)
    assert ranked[0].candidate_id == "c2"


def test_rank_tiebreak_publication_gate():
    scores = [
        CandidateScore(candidate_id="c1", final_score=0.7),
        CandidateScore(candidate_id="c2", final_score=0.7),
    ]
    gate = {"c1": False, "c2": True}
    ranked = rank_candidates(scores, publication_gate_passed=gate)
    assert ranked[0].candidate_id == "c2"
