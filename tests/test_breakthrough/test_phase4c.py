"""Phase 4C test suite: review UI actions, domain-fit config loading,
embedding monitoring, calibration diagnostics, schema v004, drift reporting.

All tests are offline-safe — no live network or Ollama calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest

from breakthrough_engine.db import Repository, init_db, _current_version
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    DraftStatus,
    EvidenceItem,
    EvidencePack,
    NoveltyDecision,
    NoveltyResult,
    PublicationDraft,
    ResearchProgram,
    ReviewAction,
    RunMode,
    RunRecord,
    RunStatus,
    SimulationResult,
    SimulationStatus,
    new_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> sqlite3.Connection:
    return init_db(in_memory=True)


def _make_repo() -> Repository:
    return Repository(_make_db())


def _make_program(domain="clean-energy", mode=RunMode.DETERMINISTIC_TEST) -> ResearchProgram:
    return ResearchProgram(
        name="test_program",
        domain=domain,
        goal="Discover novel materials and processes for renewable energy generation and storage.",
        mode=mode,
        candidate_budget=5,
        publication_threshold=0.60,
    )


def _make_candidate(
    domain="clean-energy",
    title="Perovskite-TI Hybrid Solar Cell",
    statement="Combining perovskite absorbers with topological insulator contacts will increase solar cell efficiency.",
    mechanism="Topological surface states in Bi2Te3 provide spin-momentum locked charge transport at the interface.",
    run_id="",
) -> CandidateHypothesis:
    return CandidateHypothesis(
        id=new_id(), run_id=run_id, title=title, domain=domain,
        statement=statement, mechanism=mechanism,
        expected_outcome="Efficiency exceeding 26%.",
        assumptions=["Bi2Te3 surface states survive deposition"],
        risk_flags=["Interface stability unknown"],
    )


def _make_evidence(count=4) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            id=f"ev_{i:03d}", source_type="paper", source_id=f"arxiv:2024.{i:05d}",
            title=f"Solar cell efficiency breakthrough {i}",
            quote=f"We observed significant improvement in photovoltaic efficiency using novel perovskite materials ({i}).",
            citation=f"Author{i} et al. (2024)", relevance_score=0.8 - i * 0.1,
        )
        for i in range(count)
    ]


def _setup_draft(repo):
    """Create a run and draft for review testing."""
    run = RunRecord(id="review_run", program_name="test", mode=RunMode.PRODUCTION_REVIEW, status=RunStatus.COMPLETED)
    repo.save_run(run)
    candidate = _make_candidate(run_id="review_run")
    repo.save_candidate(candidate)

    draft = PublicationDraft(
        id="draft_001", run_id="review_run", candidate_id=candidate.id,
        candidate_title=candidate.title, hypothesis=candidate.statement,
        score_breakdown={"final_score": 0.75}, evidence_summary="Evidence here.",
        status=DraftStatus.PENDING_REVIEW,
    )
    repo.save_draft(draft)
    return run, candidate, draft


# ===========================================================================
# A. Review UI Action Tests
# ===========================================================================

class TestReviewUIActions:

    def _make_app(self):
        from flask import Flask
        from breakthrough_engine.api import bp
        import breakthrough_engine.api as api_mod
        api_mod._db = init_db(in_memory=True)
        api_mod._db_path = None
        app = Flask(__name__)
        app.register_blueprint(bp)
        return app, Repository(api_mod._db)

    def test_approve_via_form(self):
        app, repo = self._make_app()
        _setup_draft(repo)
        with app.test_client() as client:
            resp = client.post(
                "/api/breakthrough/review/drafts/draft_001/approve",
                data={"reviewer": "tester", "notes": "looks good"},
                content_type="application/x-www-form-urlencoded",
            )
            assert resp.status_code == 200
            assert b"Approved" in resp.data
            # Draft should now be approved
            draft = repo.get_draft("draft_001")
            assert draft["status"] == "approved"

    def test_reject_via_form(self):
        app, repo = self._make_app()
        _setup_draft(repo)
        with app.test_client() as client:
            resp = client.post(
                "/api/breakthrough/review/drafts/draft_001/reject",
                data={"reviewer": "tester", "reason": "needs more evidence"},
                content_type="application/x-www-form-urlencoded",
            )
            assert resp.status_code == 200
            assert b"Rejected" in resp.data
            draft = repo.get_draft("draft_001")
            assert draft["status"] == "rejected"

    def test_approve_via_json(self):
        app, repo = self._make_app()
        _setup_draft(repo)
        with app.test_client() as client:
            resp = client.post(
                "/api/breakthrough/review/drafts/draft_001/approve",
                json={"reviewer": "api_user", "notes": ""},
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "approved"

    def test_reject_via_json(self):
        app, repo = self._make_app()
        _setup_draft(repo)
        with app.test_client() as client:
            resp = client.post(
                "/api/breakthrough/review/drafts/draft_001/reject",
                json={"reviewer": "api_user", "reason": "off topic"},
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "rejected"

    def test_approve_nonexistent_draft_form(self):
        app, _ = self._make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/breakthrough/review/drafts/nonexistent/approve",
                data={"reviewer": "tester"},
                content_type="application/x-www-form-urlencoded",
            )
            assert resp.status_code == 400
            assert b"Failed" in resp.data

    def test_reject_already_reviewed(self):
        app, repo = self._make_app()
        _setup_draft(repo)
        with app.test_client() as client:
            # Approve first
            client.post(
                "/api/breakthrough/review/drafts/draft_001/approve",
                json={"reviewer": "tester"},
                content_type="application/json",
            )
            # Try to reject after approve
            resp = client.post(
                "/api/breakthrough/review/drafts/draft_001/reject",
                json={"reviewer": "tester"},
                content_type="application/json",
            )
            assert resp.status_code == 400

    def test_approve_preserves_one_publication_per_run(self):
        """Second approval for same run should fail."""
        app, repo = self._make_app()
        run, cand, draft1 = _setup_draft(repo)
        # Approve first draft
        from breakthrough_engine.review import approve_draft
        pub = approve_draft(repo, "draft_001")
        assert pub is not None
        # Create second draft for same run
        cand2 = _make_candidate(run_id="review_run")
        repo.save_candidate(cand2)
        draft2 = PublicationDraft(
            id="draft_002", run_id="review_run", candidate_id=cand2.id,
            candidate_title=cand2.title, hypothesis=cand2.statement,
            status=DraftStatus.PENDING_REVIEW,
        )
        repo.save_draft(draft2)
        # Second approval should fail
        pub2 = approve_draft(repo, "draft_002")
        assert pub2 is None


# ===========================================================================
# B. Domain-Fit Config Loading Tests
# ===========================================================================

class TestDomainFitConfigLoading:

    def test_load_clean_energy_config(self):
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        config = load_domain_fit_config("clean-energy")
        assert config.domain == "clean-energy"
        assert "solar" in config.positive_keywords
        assert "crispr" in config.negative_keywords
        assert config.min_score == 0.25

    def test_load_materials_config(self):
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        config = load_domain_fit_config("materials")
        assert "alloy" in config.positive_keywords
        assert config.min_score == 0.25

    def test_load_cross_domain_config(self):
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        config = load_domain_fit_config("cross-domain")
        assert len(config.positive_keywords) == 0

    def test_fallback_unknown_domain(self):
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        config = load_domain_fit_config("quantum-computing")
        assert len(config.positive_keywords) == 0  # cross-domain fallback

    def test_config_caching(self):
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        c1 = load_domain_fit_config("clean-energy")
        c2 = load_domain_fit_config("clean-energy")
        assert c1 is c2  # same object from cache

    def test_list_domain_configs(self):
        from breakthrough_engine.domain_fit import list_domain_configs
        configs = list_domain_configs()
        assert "clean_energy" in configs
        assert "materials" in configs
        assert "cross_domain" in configs

    def test_evaluator_uses_config(self):
        from breakthrough_engine.domain_fit import DomainFitEvaluator, clear_config_cache
        clear_config_cache()
        evaluator = DomainFitEvaluator()
        candidate = _make_candidate()
        program = _make_program()
        result = evaluator.evaluate(candidate, program)
        assert result.passed
        assert len(result.matched_keywords) > 0

    def test_custom_config_dir(self):
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        with tempfile.TemporaryDirectory() as tmpdir:
            import yaml
            config_data = {
                "domain": "test-domain",
                "positive_keywords": ["alpha", "beta"],
                "negative_keywords": ["gamma"],
                "min_score": 0.5,
            }
            with open(os.path.join(tmpdir, "test-domain.yaml"), "w") as f:
                yaml.dump(config_data, f)
            config = load_domain_fit_config("test-domain", config_dir=tmpdir)
            assert config.domain == "test-domain"
            assert "alpha" in config.positive_keywords
            assert config.min_score == 0.5

    def test_materials_science_domain_lookup(self):
        """materials-science domain should match materials.yaml via partial match."""
        from breakthrough_engine.domain_fit import load_domain_fit_config, clear_config_cache
        clear_config_cache()
        config = load_domain_fit_config("materials-science")
        assert "alloy" in config.positive_keywords


# ===========================================================================
# C. Embedding Monitoring Tests
# ===========================================================================

class TestEmbeddingMonitoring:

    def test_monitor_lifecycle(self):
        from breakthrough_engine.embedding_monitor import EmbeddingMonitor
        from breakthrough_engine.embeddings import MockEmbeddingProvider, EmbeddingNoveltyDetail
        repo = _make_repo()
        monitor = EmbeddingMonitor(repo)
        provider = MockEmbeddingProvider()

        monitor.start_run("run_001", provider, similarity_threshold=0.88, warn_threshold=0.78)

        # Record some evaluations
        monitor.record_evaluation(EmbeddingNoveltyDetail(
            embedding_similarity_max=0.75,
            nearest_neighbors=[{"title": "Paper A", "similarity": 0.75, "source": "local"}],
        ))
        monitor.record_evaluation(EmbeddingNoveltyDetail(
            embedding_similarity_max=0.92,
            nearest_neighbors=[{"title": "Paper B", "similarity": 0.92, "source": "local"}],
            blocked_by_prior_art=True,
        ))
        monitor.record_evaluation(EmbeddingNoveltyDetail(
            embedding_similarity_max=0.82,
            nearest_neighbors=[{"title": "Paper C", "similarity": 0.82, "source": "retrieved"}],
        ))

        stats = monitor.finish_run()
        assert stats is not None
        assert stats.candidates_evaluated == 3
        assert stats.blocked_count == 1
        assert stats.warned_count == 1  # 0.82 >= 0.78 and not blocked
        assert stats.max_similarity == 0.92
        assert len(stats.top_k_similarities) == 3

    def test_monitor_persists_to_db(self):
        from breakthrough_engine.embedding_monitor import EmbeddingMonitor
        from breakthrough_engine.embeddings import MockEmbeddingProvider, EmbeddingNoveltyDetail
        repo = _make_repo()
        monitor = EmbeddingMonitor(repo)
        provider = MockEmbeddingProvider()

        monitor.start_run("run_persist", provider)
        monitor.record_evaluation(EmbeddingNoveltyDetail(embedding_similarity_max=0.5))
        monitor.finish_run()

        result = repo.get_embedding_monitor("run_persist")
        assert result is not None
        assert result["candidates_evaluated"] == 1
        assert result["embedding_model"] == "mock"

    def test_drift_report_empty(self):
        from breakthrough_engine.embedding_monitor import EmbeddingMonitor
        repo = _make_repo()
        monitor = EmbeddingMonitor(repo)
        report = monitor.get_drift_report()
        assert report["status"] == "no_data"

    def test_drift_report_with_data(self):
        from breakthrough_engine.embedding_monitor import EmbeddingMonitor
        from breakthrough_engine.embeddings import MockEmbeddingProvider, EmbeddingNoveltyDetail
        repo = _make_repo()
        monitor = EmbeddingMonitor(repo)
        provider = MockEmbeddingProvider()

        for i in range(3):
            monitor.start_run(f"run_{i:03d}", provider)
            monitor.record_evaluation(EmbeddingNoveltyDetail(
                embedding_similarity_max=0.5 + i * 0.1,
                nearest_neighbors=[{"title": f"Paper {i}", "similarity": 0.5 + i * 0.1, "source": "local"}],
            ))
            monitor.finish_run()

        report = monitor.get_drift_report()
        assert report["status"] == "ok"
        assert report["runs_analyzed"] == 3
        assert len(report["trend"]) == 3
        assert "avg_max_similarity" in report["summary"]

    def test_repeated_neighbors_detected(self):
        from breakthrough_engine.embedding_monitor import EmbeddingMonitor
        from breakthrough_engine.embeddings import MockEmbeddingProvider, EmbeddingNoveltyDetail
        repo = _make_repo()
        monitor = EmbeddingMonitor(repo)
        provider = MockEmbeddingProvider()

        # Same neighbor appears in 3 runs
        for i in range(3):
            monitor.start_run(f"run_nn_{i}", provider)
            monitor.record_evaluation(EmbeddingNoveltyDetail(
                embedding_similarity_max=0.8,
                nearest_neighbors=[{"title": "Repeated Paper", "similarity": 0.8, "source": "local"}],
            ))
            monitor.finish_run()

        report = monitor.get_drift_report()
        repeated = [r for r in report["repeated_neighbors"] if "Repeated Paper" in r["title"]]
        assert len(repeated) > 0
        assert repeated[0]["appearances"] >= 2


# ===========================================================================
# D. Calibration Diagnostics Tests
# ===========================================================================

class TestCalibrationDiagnostics:

    def test_save_and_get_calibration(self):
        repo = _make_repo()
        repo.save_calibration_diagnostic({
            "run_id": "cal_run_001",
            "lexical_block_count": 1,
            "embedding_block_count": 2,
            "domain_fit_fail_count": 0,
            "domain_fit_mean_score": 0.75,
            "publication_pass_count": 3,
            "publication_fail_count": 1,
            "publication_fail_reasons": ["score below threshold"],
            "draft_count": 1,
            "candidate_count": 5,
            "active_thresholds": {"publication_threshold": 0.60},
        })
        result = repo.get_calibration_diagnostic("cal_run_001")
        assert result is not None
        assert result["lexical_block_count"] == 1
        assert result["embedding_block_count"] == 2
        assert result["candidate_count"] == 5

    def test_list_calibration_diagnostics(self):
        repo = _make_repo()
        for i in range(3):
            repo.save_calibration_diagnostic({
                "run_id": f"cal_{i}",
                "candidate_count": i + 1,
            })
        results = repo.list_calibration_diagnostics(limit=10)
        assert len(results) == 3


# ===========================================================================
# E. Schema v004 Tests
# ===========================================================================

class TestMigrationV004:

    def test_schema_version_is_4(self):
        db = _make_db()
        assert _current_version(db) >= 4

    def test_embedding_monitor_table_exists(self):
        db = _make_db()
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bt_%'"
        ).fetchall()]
        assert "bt_embedding_monitor" in tables

    def test_calibration_diagnostics_table_exists(self):
        db = _make_db()
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bt_%'"
        ).fetchall()]
        assert "bt_calibration_diagnostics" in tables

    def test_embedding_monitor_crud(self):
        repo = _make_repo()
        repo.save_embedding_monitor({
            "run_id": "em_test",
            "embedding_model": "nomic-embed-text",
            "embedding_dim": 768,
            "candidates_evaluated": 5,
            "blocked_count": 1,
            "max_similarity": 0.92,
            "mean_similarity": 0.65,
        })
        result = repo.get_embedding_monitor("em_test")
        assert result is not None
        assert result["embedding_model"] == "nomic-embed-text"
        assert result["max_similarity"] == 0.92

    def test_list_embedding_monitors(self):
        repo = _make_repo()
        for i in range(3):
            repo.save_embedding_monitor({
                "run_id": f"em_{i}",
                "candidates_evaluated": i + 1,
            })
        results = repo.list_embedding_monitors(limit=10)
        assert len(results) == 3


# ===========================================================================
# F. Review UI HTML Content Tests
# ===========================================================================

class TestReviewUIContent:

    def _make_app(self):
        from flask import Flask
        from breakthrough_engine.api import bp
        import breakthrough_engine.api as api_mod
        api_mod._db = init_db(in_memory=True)
        api_mod._db_path = None
        app = Flask(__name__)
        app.register_blueprint(bp)
        return app, Repository(api_mod._db)

    def test_review_queue_with_draft(self):
        app, repo = self._make_app()
        _setup_draft(repo)
        with app.test_client() as client:
            resp = client.get("/api/breakthrough/view/review")
            assert resp.status_code == 200
            assert b"Perovskite" in resp.data
            assert b"btn-approve" in resp.data
            assert b"btn-reject" in resp.data
            assert b"confirm(" in resp.data  # JS confirmation

    def test_candidate_detail_html(self):
        app, repo = self._make_app()
        run, candidate, _ = _setup_draft(repo)
        # Save score and domain fit for the candidate
        score = CandidateScore(
            candidate_id=candidate.id, novelty_score=0.8,
            plausibility_score=0.7, final_score=0.75,
        )
        repo.save_score(score)
        repo.save_domain_fit({
            "candidate_id": candidate.id, "domain": "clean-energy",
            "domain_fit_score": 0.8, "title_relevance": 0.7,
            "statement_relevance": 0.6, "mechanism_relevance": 0.5,
            "evidence_relevance": 0.4, "matched_keywords": ["solar"],
        })
        with app.test_client() as client:
            resp = client.get(f"/api/breakthrough/view/candidate/{candidate.id}")
            assert resp.status_code == 200

    def test_thresholds_endpoint(self):
        app, _ = self._make_app()
        with app.test_client() as client:
            resp = client.get("/api/breakthrough/view/thresholds")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["publication_threshold"] == 0.60
            assert data["novelty_embedding_block"] == 0.88

    def test_embedding_drift_endpoint_empty(self):
        app, _ = self._make_app()
        with app.test_client() as client:
            resp = client.get("/api/breakthrough/view/embedding-drift")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "no_data"


# ===========================================================================
# G. Orchestrator Integration with Phase 4C
# ===========================================================================

class TestOrchestratorPhase4C:

    def test_deterministic_run_saves_embedding_monitor(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        program = _make_program(mode=RunMode.DETERMINISTIC_TEST)
        repo = _make_repo()
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()

        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION)
        monitor = repo.get_embedding_monitor(run.id)
        assert monitor is not None
        assert monitor["candidates_evaluated"] >= 0

    def test_deterministic_run_saves_calibration(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        program = _make_program(mode=RunMode.DETERMINISTIC_TEST)
        repo = _make_repo()
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()

        cal = repo.get_calibration_diagnostic(run.id)
        assert cal is not None
        assert cal["candidate_count"] > 0

    def test_review_mode_creates_draft_with_monitoring(self):
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        program = _make_program(mode=RunMode.PRODUCTION_REVIEW)
        repo = _make_repo()
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()

        # Should have monitoring data
        monitor = repo.get_embedding_monitor(run.id)
        assert monitor is not None

        # If a draft was created, verify it exists
        draft = repo.get_draft_by_run(run.id)
        if draft:
            assert draft["status"] == "pending_review"


# ===========================================================================
# H. Golden Calibration Edge Cases (Phase 4C additions)
# ===========================================================================

class TestCalibrationGoldenCasesPhase4C:

    def test_high_similarity_acceptable_domain_distinction(self):
        """Two candidates with high text similarity but different domains should not block."""
        from breakthrough_engine.embeddings import EmbeddingNoveltyEngine, MockEmbeddingProvider
        provider = MockEmbeddingProvider()
        engine = EmbeddingNoveltyEngine(provider=provider, similarity_threshold=0.88)
        # Candidate about solar
        candidate = _make_candidate(
            title="Novel perovskite solar cell architecture",
            statement="Using halide perovskites with tin-based electrodes for improved solar energy conversion.",
            mechanism="Tin electrodes reduce lead toxicity while maintaining bandgap alignment.",
        )
        # Prior about batteries (different domain application)
        prior = [{
            "title": "Novel perovskite battery electrode design",
            "text": "Using halide perovskites with tin-based electrodes for improved battery energy storage capacity.",
            "source": "local_candidate",
            "source_id": "prior_distinct",
        }]
        detail = engine.evaluate(candidate, prior_texts=prior)
        # With mock embeddings, word overlap drives similarity
        # These share many words but differ in application context
        assert detail.embedding_similarity_max > 0.3
        assert not detail.blocked_by_prior_art

    def test_candidate_should_warn_not_block(self):
        """Candidate at warn threshold should not be blocked."""
        from breakthrough_engine.embeddings import EmbeddingNoveltyEngine, MockEmbeddingProvider
        provider = MockEmbeddingProvider()
        engine = EmbeddingNoveltyEngine(provider=provider, similarity_threshold=0.95, warn_threshold=0.60)
        candidate = _make_candidate()
        prior = [{
            "title": "Related solar cell research",
            "text": "Solar cell efficiency improvements using advanced materials and electrode designs.",
            "source": "local_candidate",
            "source_id": "prior_related",
        }]
        detail = engine.evaluate(candidate, prior_texts=prior)
        # Should warn but not block
        if detail.embedding_similarity_max >= 0.60 and detail.embedding_similarity_max < 0.95:
            assert not detail.blocked_by_prior_art

    def test_off_domain_with_good_evidence_still_fails_domain_fit(self):
        """Off-domain candidate with relevant-looking evidence should still fail domain-fit."""
        from breakthrough_engine.domain_fit import DomainFitEvaluator, clear_config_cache
        clear_config_cache()
        evaluator = DomainFitEvaluator()
        candidate = _make_candidate(
            title="CRISPR Gene Editing for Alzheimer's Treatment",
            statement="CRISPR-Cas9 targets amyloid precursor protein in neurons.",
            mechanism="Guide RNA directs Cas9 to APP gene promoter for selective gene silencing.",
        )
        # Evidence that mentions energy keywords doesn't help
        evidence = [EvidenceItem(
            id="ev_bio", source_type="paper", source_id="pmid:12345",
            title="Gene therapy advances in solar-powered biomedical devices",
            quote="Solar-powered gene therapy devices improve efficiency of CRISPR delivery.",
            citation="BioAuthor (2024)", relevance_score=0.8,
        )]
        program = _make_program(domain="clean-energy")
        result = evaluator.evaluate(candidate, program, evidence=evidence)
        # Should fail or score low due to CRISPR being off-domain
        assert result.domain_fit_score < 0.5 or len(result.mismatch_flags) > 0
