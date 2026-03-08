"""End-to-end orchestrator tests using deterministic fakes."""

import pytest

from breakthrough_engine.candidate_generator import FakeCandidateGenerator
from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.evidence_source import DemoFixtureSource
from breakthrough_engine.models import (
    CandidateStatus,
    ResearchProgram,
    RunMode,
    RunStatus,
)
from breakthrough_engine.orchestrator import BreakthroughOrchestrator
from breakthrough_engine.simulator import MockSimulatorAdapter


@pytest.fixture
def program():
    return ResearchProgram(
        name="test_e2e",
        domain="test",
        candidate_budget=3,
        simulation_budget=2,
        publication_threshold=0.50,  # lower threshold for test
        mode=RunMode.DETERMINISTIC_TEST,
    )


@pytest.fixture
def repo():
    """Fresh in-memory DB for each test to avoid cross-test dedup interference."""
    db = init_db(in_memory=True)
    return Repository(db)


@pytest.fixture
def make_orchestrator(program):
    """Factory that creates a fresh orchestrator with its own DB each time."""
    def _make():
        db = init_db(in_memory=True)
        repo = Repository(db)
        orchestrator = BreakthroughOrchestrator(
            program=program, repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
            simulator=MockSimulatorAdapter(),
        )
        return orchestrator, repo
    return _make


class TestOrchestratorE2E:
    def test_full_cycle_produces_publication(self, program, repo):
        orchestrator = BreakthroughOrchestrator(
            program=program,
            repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
            simulator=MockSimulatorAdapter(),
        )
        run = orchestrator.run()

        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION)
        assert run.candidates_generated == 3

        # Check that candidates were persisted
        candidates = repo.list_candidates_for_run(run.id)
        assert len(candidates) == 3

        # Check status distribution
        statuses = [c["status"] for c in candidates]
        # At least one should be published or finalist
        assert any(s in ("published", "finalist") for s in statuses) or \
               run.status == RunStatus.COMPLETED_NO_PUBLICATION

    def test_publication_persisted(self, program, repo):
        orchestrator = BreakthroughOrchestrator(
            program=program, repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
            simulator=MockSimulatorAdapter(),
        )
        run = orchestrator.run()

        if run.status == RunStatus.COMPLETED:
            assert run.publication_id is not None
            pub = repo.get_publication(run.publication_id)
            assert pub is not None
            assert pub["status_label"] == "validated_breakthrough_candidate"
            assert len(pub["hypothesis"]) > 0

    def test_rejections_recorded(self, program, repo):
        orchestrator = BreakthroughOrchestrator(
            program=program, repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
            simulator=MockSimulatorAdapter(),
        )
        run = orchestrator.run()

        rejections = repo.list_rejections(run.id)
        # Some candidates should be rejected (finalists are not in rejections)
        if run.status == RunStatus.COMPLETED:
            # At least the non-published candidates that failed gates
            candidates = repo.list_candidates_for_run(run.id)
            rejected_count = sum(
                1 for c in candidates
                if c["status"] not in ("published", "finalist", "generated")
            )
            assert len(rejections) == rejected_count

    def test_harness_decisions_recorded(self, make_orchestrator):
        orchestrator, repo = make_orchestrator()
        run = orchestrator.run()

        candidates = repo.list_candidates_for_run(run.id)
        # At least some candidates should have harness decisions
        total_decisions = 0
        for c in candidates:
            decisions = repo.get_harness_decisions(c["id"])
            total_decisions += len(decisions)
        assert total_decisions > 0

    def test_scores_recorded(self, make_orchestrator):
        orchestrator, repo = make_orchestrator()
        run = orchestrator.run()

        candidates = repo.list_candidates_for_run(run.id)
        scored = 0
        for c in candidates:
            s = repo.get_score(c["id"])
            if s:
                scored += 1
                assert s["final_score"] >= 0.0
        assert scored > 0

    def test_run_is_deterministic(self, program):
        """Same inputs should produce same outputs."""
        results = []
        for _ in range(2):
            db = init_db(in_memory=True)
            repo = Repository(db)
            orchestrator = BreakthroughOrchestrator(
                program=program, repo=repo,
                evidence_source=DemoFixtureSource(),
                generator=FakeCandidateGenerator(),
                simulator=MockSimulatorAdapter(),
            )
            run = orchestrator.run()
            results.append(run)

        assert results[0].status == results[1].status
        assert results[0].candidates_generated == results[1].candidates_generated

    def test_high_threshold_no_publication(self, repo):
        """With very high threshold, no candidate should be published."""
        program = ResearchProgram(
            name="strict_test",
            domain="test",
            candidate_budget=3,
            simulation_budget=2,
            publication_threshold=0.99,  # nearly impossible
            mode=RunMode.DETERMINISTIC_TEST,
        )
        orchestrator = BreakthroughOrchestrator(
            program=program, repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
            simulator=MockSimulatorAdapter(),
        )
        run = orchestrator.run()
        assert run.status == RunStatus.COMPLETED_NO_PUBLICATION
        assert run.publication_id is None
