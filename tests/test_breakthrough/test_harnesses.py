"""Tests for the four deterministic harnesses."""

import pytest

from breakthrough_engine.harnesses import (
    run_evidence_harness,
    run_hypothesis_harness,
    run_publication_gate,
    run_simulation_harness,
)
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    EvidenceItem,
    EvidencePack,
    SimulationResult,
    SimulationSpec,
    SimulationStatus,
)


# ---------------------------------------------------------------------------
# Hypothesis Harness
# ---------------------------------------------------------------------------

def _make_good_candidate(**overrides):
    defaults = dict(
        title="Test Candidate",
        domain="test",
        statement="A novel combination of perovskite absorbers with topological insulator contacts increases solar cell efficiency.",
        mechanism="Topological surface states reduce recombination at the perovskite-contact interface by providing spin-locked transport.",
        expected_outcome="Power conversion efficiency exceeding 26% in single-junction cells measurable via PL quantum yield.",
        assumptions=["Interface lattice mismatch is manageable"],
        risk_flags=[],
        testability_window_hours=48.0,
    )
    defaults.update(overrides)
    return CandidateHypothesis(**defaults)


class TestHypothesisHarness:
    def test_good_candidate_passes(self):
        c = _make_good_candidate()
        d = run_hypothesis_harness(c)
        assert d.passed
        assert d.failed_rules == []

    def test_empty_statement_fails(self):
        c = _make_good_candidate(statement="")
        d = run_hypothesis_harness(c)
        assert not d.passed
        assert "empty_statement" in d.failed_rules

    def test_short_statement_fails(self):
        c = _make_good_candidate(statement="Too short")
        d = run_hypothesis_harness(c)
        assert not d.passed
        assert "statement_too_short" in d.failed_rules

    def test_missing_mechanism_fails(self):
        c = _make_good_candidate(mechanism="short")
        d = run_hypothesis_harness(c)
        assert not d.passed
        assert "mechanism_missing_or_vague" in d.failed_rules

    def test_missing_outcome_fails(self):
        c = _make_good_candidate(expected_outcome="short")
        d = run_hypothesis_harness(c)
        assert not d.passed
        assert "expected_outcome_missing" in d.failed_rules

    def test_generic_phrase_fails(self):
        c = _make_good_candidate(
            statement="Further research is needed to understand the effect of perovskite materials on solar cells."
        )
        d = run_hypothesis_harness(c)
        assert not d.passed
        assert any("generic_phrase" in r for r in d.failed_rules)

    def test_zero_testability_fails(self):
        c = _make_good_candidate(testability_window_hours=0)
        d = run_hypothesis_harness(c)
        assert not d.passed
        assert "untestable_zero_window" in d.failed_rules

    def test_near_duplicate_fails(self):
        c = _make_good_candidate()
        priors = [c.statement]  # exact same statement
        d = run_hypothesis_harness(c, prior_statements=priors)
        assert not d.passed
        assert "near_duplicate_of_prior_candidate" in d.failed_rules

    def test_no_assumptions_warns(self):
        c = _make_good_candidate(assumptions=[])
        d = run_hypothesis_harness(c)
        assert d.passed  # warning, not failure
        assert "no_assumptions_disclosed" in d.warnings


# ---------------------------------------------------------------------------
# Evidence Harness
# ---------------------------------------------------------------------------

def _make_evidence_pack(n_items=3, **overrides):
    items = []
    for i in range(n_items):
        items.append(EvidenceItem(
            source_type="paper",
            source_id=f"src_{i}",
            title=f"Paper {i}",
            quote=f"This is evidence quote number {i} from the paper.",
            citation=f"Author et al., Journal, 2024",
            relevance_score=0.8,
        ))
    defaults = dict(candidate_id="c1", items=items, source_diversity_count=n_items)
    defaults.update(overrides)
    return EvidencePack(**defaults)


class TestEvidenceHarness:
    def test_good_evidence_passes(self):
        pack = _make_evidence_pack(3)
        d = run_evidence_harness(pack, minimum_evidence=2)
        assert d.passed

    def test_insufficient_evidence_fails(self):
        pack = _make_evidence_pack(1)
        d = run_evidence_harness(pack, minimum_evidence=2)
        assert not d.passed
        assert any("insufficient" in r for r in d.failed_rules)

    def test_missing_quote_fails(self):
        pack = _make_evidence_pack(2)
        pack.items[0].quote = ""
        d = run_evidence_harness(pack, minimum_evidence=2)
        assert not d.passed
        assert any("missing_quote" in r for r in d.failed_rules)

    def test_missing_citation_fails(self):
        pack = _make_evidence_pack(2)
        pack.items[1].citation = ""
        d = run_evidence_harness(pack, minimum_evidence=2)
        assert not d.passed
        assert any("missing_citation" in r for r in d.failed_rules)

    def test_low_diversity_warns(self):
        pack = _make_evidence_pack(2)
        pack.items[0].source_id = "same_source"
        pack.items[1].source_id = "same_source"
        d = run_evidence_harness(pack, minimum_evidence=2)
        assert d.passed  # warning, not failure
        assert "low_source_diversity" in d.warnings

    def test_certainty_language_warns(self):
        pack = _make_evidence_pack(2)
        pack.items[0].quote = "This proves conclusively that the effect exists."
        d = run_evidence_harness(pack, minimum_evidence=2)
        assert d.passed  # warning
        assert any("certainty" in w for w in d.warnings)


# ---------------------------------------------------------------------------
# Simulation Harness
# ---------------------------------------------------------------------------

class TestSimulationHarness:
    def test_good_spec_passes(self):
        spec = SimulationSpec(
            candidate_id="c1",
            simulator="mock",
            objective="Test hypothesis",
            parameters={"temperature_k": 300},
            estimated_runtime_minutes=5.0,
        )
        d = run_simulation_harness(spec, runtime_budget_minutes=60)
        assert d.passed

    def test_disallowed_simulator_fails(self):
        spec = SimulationSpec(
            candidate_id="c1", simulator="unknown_sim",
            estimated_runtime_minutes=5.0,
        )
        d = run_simulation_harness(spec)
        assert not d.passed
        assert any("not_allowed" in r for r in d.failed_rules)

    def test_runtime_over_budget_fails(self):
        spec = SimulationSpec(
            candidate_id="c1", simulator="mock",
            estimated_runtime_minutes=120.0,
        )
        d = run_simulation_harness(spec, runtime_budget_minutes=60)
        assert not d.passed
        assert any("runtime_exceeds" in r for r in d.failed_rules)

    def test_parameter_out_of_bounds_fails(self):
        spec = SimulationSpec(
            candidate_id="c1", simulator="mock",
            parameters={"velocity_ms": 4e8},  # faster than light
            estimated_runtime_minutes=5.0,
        )
        d = run_simulation_harness(spec)
        assert not d.passed
        assert any("out_of_bounds" in r for r in d.failed_rules)

    def test_negative_temperature_fails(self):
        spec = SimulationSpec(
            candidate_id="c1", simulator="mock",
            parameters={"temperature_k": -10},
            estimated_runtime_minutes=5.0,
        )
        d = run_simulation_harness(spec)
        assert not d.passed
        assert any("negative_absolute_temperature" in r or "out_of_bounds" in r
                    for r in d.failed_rules)


# ---------------------------------------------------------------------------
# Publication Gate
# ---------------------------------------------------------------------------

class TestPublicationGate:
    def test_good_candidate_passes_gate(self):
        c = _make_good_candidate()
        score = CandidateScore(
            candidate_id=c.id,
            final_score=0.75,
        )
        pack = _make_evidence_pack(2)
        pack.candidate_id = c.id
        sim = SimulationResult(
            candidate_id=c.id,
            status=SimulationStatus.COMPLETED,
            pass_fail_summary="OK",
        )
        d = run_publication_gate(c, score, pack, sim, publication_threshold=0.60)
        assert d.passed

    def test_low_score_fails(self):
        c = _make_good_candidate()
        score = CandidateScore(candidate_id=c.id, final_score=0.40)
        pack = _make_evidence_pack(2)
        d = run_publication_gate(c, score, pack, None, publication_threshold=0.60)
        assert not d.passed
        assert any("score_below_threshold" in r for r in d.failed_rules)

    def test_no_evidence_fails(self):
        c = _make_good_candidate()
        score = CandidateScore(candidate_id=c.id, final_score=0.75)
        d = run_publication_gate(c, score, None, None)
        assert not d.passed
        assert "no_evidence_attached" in d.failed_rules

    def test_no_assumptions_fails(self):
        c = _make_good_candidate(assumptions=[])
        score = CandidateScore(candidate_id=c.id, final_score=0.75)
        pack = _make_evidence_pack(2)
        d = run_publication_gate(c, score, pack, None)
        assert not d.passed
        assert "assumptions_not_disclosed" in d.failed_rules

    def test_failed_simulation_fails(self):
        c = _make_good_candidate()
        score = CandidateScore(candidate_id=c.id, final_score=0.75)
        pack = _make_evidence_pack(2)
        sim = SimulationResult(
            candidate_id=c.id, status=SimulationStatus.FAILED,
        )
        d = run_publication_gate(c, score, pack, sim)
        assert not d.passed
        assert "simulation_failed" in d.failed_rules

    def test_claims_confirmed_discovery_fails(self):
        c = _make_good_candidate(
            statement="This is a confirmed discovery that perovskite cells achieve 30% efficiency."
        )
        score = CandidateScore(candidate_id=c.id, final_score=0.75)
        pack = _make_evidence_pack(2)
        d = run_publication_gate(c, score, pack, None)
        assert not d.passed
        assert "claims_confirmed_discovery" in d.failed_rules
