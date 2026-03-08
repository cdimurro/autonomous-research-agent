"""Tests for database initialization and repository layer."""

import pytest

from breakthrough_engine.db import Repository, init_db, _current_version
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    EvidenceItem,
    EvidencePack,
    HarnessDecision,
    PublicationRecord,
    RunRecord,
    RunStatus,
    SimulationResult,
    SimulationSpec,
    SimulationStatus,
)


@pytest.fixture
def db():
    return init_db(in_memory=True)


@pytest.fixture
def repo(db):
    return Repository(db)


class TestDbInit:
    def test_init_creates_tables(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bt_%' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "bt_runs" in table_names
        assert "bt_candidates" in table_names
        assert "bt_publications" in table_names
        assert "bt_rejections" in table_names
        assert "bt_schema_version" in table_names

    def test_init_is_idempotent(self, db):
        # Running init again should not fail
        v1 = _current_version(db)
        db2 = init_db(in_memory=True)
        v2 = _current_version(db2)
        assert v1 == v2

    def test_schema_version_tracked(self, db):
        version = _current_version(db)
        assert version >= 1


class TestRunRepository:
    def test_save_and_get_run(self, repo):
        run = RunRecord(program_name="test_prog")
        repo.save_run(run)
        loaded = repo.get_run(run.id)
        assert loaded is not None
        assert loaded["program_name"] == "test_prog"
        assert loaded["status"] == "started"

    def test_list_runs(self, repo):
        for i in range(3):
            repo.save_run(RunRecord(program_name=f"prog_{i}"))
        runs = repo.list_runs()
        assert len(runs) == 3


class TestCandidateRepository:
    def test_save_and_get_candidate(self, repo):
        run = RunRecord(program_name="test")
        repo.save_run(run)

        c = CandidateHypothesis(
            run_id=run.id, title="Test", domain="test",
            statement="Test statement for candidate",
            mechanism="Test mechanism description",
            expected_outcome="Test outcome description",
        )
        repo.save_candidate(c)
        loaded = repo.get_candidate(c.id)
        assert loaded is not None
        assert loaded["title"] == "Test"

    def test_update_status(self, repo):
        run = RunRecord(program_name="test")
        repo.save_run(run)

        c = CandidateHypothesis(
            run_id=run.id, title="Test", domain="test",
            statement="s", mechanism="m", expected_outcome="o",
        )
        repo.save_candidate(c)
        repo.update_candidate_status(c.id, CandidateStatus.PUBLISHED)
        loaded = repo.get_candidate(c.id)
        assert loaded["status"] == "published"

    def test_list_candidates_for_run(self, repo):
        run = RunRecord(program_name="test")
        repo.save_run(run)
        for i in range(3):
            c = CandidateHypothesis(
                run_id=run.id, title=f"C{i}", domain="test",
                statement="s", mechanism="m", expected_outcome="o",
            )
            repo.save_candidate(c)
        candidates = repo.list_candidates_for_run(run.id)
        assert len(candidates) == 3


class TestPublicationRepository:
    def test_save_and_get_publication(self, repo):
        run = RunRecord(program_name="test")
        repo.save_run(run)

        pub = PublicationRecord(
            run_id=run.id, candidate_id="c1",
            candidate_title="Test Pub", hypothesis="Test hypothesis",
        )
        repo.save_publication(pub)
        loaded = repo.get_publication(pub.id)
        assert loaded is not None
        assert loaded["candidate_title"] == "Test Pub"
        assert loaded["status_label"] == "validated_breakthrough_candidate"

    def test_list_publications(self, repo):
        run = RunRecord(program_name="test")
        repo.save_run(run)
        for i in range(2):
            pub = PublicationRecord(
                run_id=run.id, candidate_id=f"c{i}",
                candidate_title=f"Pub {i}", hypothesis=f"H{i}",
            )
            repo.save_publication(pub)
        pubs = repo.list_publications()
        assert len(pubs) == 2


class TestRejectionRepository:
    def test_save_and_list_rejections(self, repo):
        run = RunRecord(program_name="test")
        repo.save_run(run)
        repo.save_rejection(
            run_id=run.id, candidate_id="c1",
            candidate_title="Failed Candidate",
            status=CandidateStatus.HYPOTHESIS_FAILED,
            reason="Too generic",
            harness_name="hypothesis_legality",
            failed_rules=["generic_phrase_detected"],
        )
        rejections = repo.list_rejections(run.id)
        assert len(rejections) == 1
        assert rejections[0]["rejection_reason"] == "Too generic"


class TestHarnessDecisionRepository:
    def test_save_and_get_decisions(self, repo):
        d = HarnessDecision(
            harness_name="hypothesis_legality",
            candidate_id="c1",
            passed=True,
            explanation="All checks passed",
        )
        repo.save_harness_decision(d)
        decisions = repo.get_harness_decisions("c1")
        assert len(decisions) == 1
        assert decisions[0]["passed"] == 1


class TestScoreRepository:
    def test_save_and_get_score(self, repo):
        score = CandidateScore(
            candidate_id="c1",
            novelty_score=0.8,
            final_score=0.72,
        )
        repo.save_score(score)
        loaded = repo.get_score("c1")
        assert loaded is not None
        assert abs(loaded["novelty_score"] - 0.8) < 0.001
        assert abs(loaded["final_score"] - 0.72) < 0.001
