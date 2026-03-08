"""Tests for domain models."""

from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    EvidenceItem,
    EvidencePack,
    RunMode,
    RunRecord,
    RunStatus,
    ResearchProgram,
    SimulationSpec,
)


def test_candidate_score_compute_final():
    score = CandidateScore(
        candidate_id="test",
        novelty_score=0.8,
        plausibility_score=0.7,
        impact_score=0.9,
        validation_cost_score=0.3,
        evidence_strength_score=0.75,
        simulation_readiness_score=0.6,
    )
    final = score.compute_final()
    # 0.8*0.2 + 0.7*0.2 + 0.9*0.2 + 0.75*0.2 + 0.6*0.1 + (1-0.3)*0.1
    expected = 0.16 + 0.14 + 0.18 + 0.15 + 0.06 + 0.07
    assert abs(final - expected) < 0.001


def test_candidate_status_enum():
    assert CandidateStatus.GENERATED.value == "generated"
    assert CandidateStatus.PUBLISHED.value == "published"
    assert CandidateStatus.DEDUP_REJECTED.value == "dedup_rejected"


def test_run_mode_enum():
    assert RunMode.DETERMINISTIC_TEST.value == "deterministic_test"
    assert RunMode.DEMO_LOCAL.value == "demo_local"


def test_research_program_defaults():
    prog = ResearchProgram(name="test", domain="test-domain")
    assert prog.candidate_budget == 10
    assert prog.publication_threshold == 0.60
    assert prog.mode == RunMode.DEMO_LOCAL
    assert sum(prog.scoring_weights.values()) == 1.0


def test_evidence_pack_creation():
    items = [
        EvidenceItem(source_type="paper", source_id="p1", title="T1",
                     quote="Q1", citation="C1", relevance_score=0.8),
        EvidenceItem(source_type="paper", source_id="p2", title="T2",
                     quote="Q2", citation="C2", relevance_score=0.7),
    ]
    pack = EvidencePack(candidate_id="c1", items=items, source_diversity_count=2)
    assert len(pack.items) == 2
    assert pack.source_diversity_count == 2
