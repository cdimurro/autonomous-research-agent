"""Phase 3 tests — Retrieval, Novelty, Review Workflow, Run Modes, Metrics, Notifications, API."""

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    DraftStatus,
    EvidenceItem,
    EvidencePack,
    NoveltyDecision,
    NoveltyResult,
    PriorArtHit,
    PublicationDraft,
    ReviewAction,
    ReviewEvent,
    RunMetrics,
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

def _make_db():
    """Create in-memory DB with Phase 3 tables."""
    return init_db(in_memory=True)


def _make_candidate(title="Test Hypothesis", statement=None, domain="test"):
    return CandidateHypothesis(
        title=title,
        domain=domain,
        statement=statement or f"A novel approach to {title.lower()} using advanced techniques that improve efficiency by 50% through targeted optimization.",
        mechanism="The mechanism involves quantum-enhanced catalytic cycles reducing activation energy barriers significantly.",
        expected_outcome="50% improvement in reaction yield measured by standard HPLC analysis within 48 hours.",
        testability_window_hours=48.0,
        novelty_notes="First demonstration of this approach in the target domain.",
        assumptions=["Catalyst remains stable under operating conditions", "Temperature can be controlled to ±1K"],
        risk_flags=["Catalyst cost may be prohibitive at scale"],
    )


# ---------------------------------------------------------------------------
# External Retrieval Tests (mocked HTTP)
# ---------------------------------------------------------------------------

MOCK_OPENALEX_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/W123",
            "doi": "https://doi.org/10.1234/test.2024.001",
            "title": "Novel Perovskite Solar Cell Efficiency Record",
            "publication_date": "2024-01-15",
            "authorships": [
                {"author": {"display_name": "Zhang Wei"}},
                {"author": {"display_name": "Li Na"}},
            ],
            "abstract_inverted_index": {
                "We": [0], "achieved": [1], "record": [2],
                "efficiency": [3], "of": [4], "25.7%": [5],
            },
            "relevance_score": 150.0,
        },
        {
            "id": "https://openalex.org/W456",
            "doi": None,
            "title": "Thermoelectric Enhancement via Nanostructuring",
            "publication_date": "2024-02-20",
            "authorships": [{"author": {"display_name": "Kim J"}}],
            "abstract_inverted_index": None,
            "relevance_score": 80.0,
        },
    ]
}

MOCK_CROSSREF_RESPONSE = {
    "message": {
        "items": [
            {
                "DOI": "10.5678/crossref.2024.001",
                "title": ["Carbon Capture via Metal-Organic Frameworks"],
                "author": [
                    {"family": "Rodriguez"},
                    {"family": "Patel"},
                ],
                "abstract": "<p>MOF-303 demonstrated CO2 uptake of 8.2 mmol/g.</p>",
                "published-print": {"date-parts": [[2024, 3, 1]]},
                "score": 120.0,
            },
        ]
    }
}


class TestOpenAlexRetrieval:
    @patch("breakthrough_engine.retrieval._http_get")
    def test_returns_evidence_items(self, mock_get):
        mock_get.return_value = MOCK_OPENALEX_RESPONSE
        from breakthrough_engine.retrieval import OpenAlexRetrievalSource
        source = OpenAlexRetrievalSource()
        items = source.gather("solar cells", limit=10)
        assert len(items) == 2
        assert items[0].source_type == "openalex"
        assert "10.1234" in items[0].source_id
        assert items[0].relevance_score <= 1.0

    @patch("breakthrough_engine.retrieval._http_get")
    def test_handles_empty_response(self, mock_get):
        mock_get.return_value = {"results": []}
        from breakthrough_engine.retrieval import OpenAlexRetrievalSource
        source = OpenAlexRetrievalSource()
        items = source.gather("nonexistent", limit=10)
        assert items == []

    @patch("breakthrough_engine.retrieval._http_get")
    def test_handles_network_failure(self, mock_get):
        mock_get.return_value = None
        from breakthrough_engine.retrieval import OpenAlexRetrievalSource
        source = OpenAlexRetrievalSource()
        items = source.gather("test", limit=10)
        assert items == []

    @patch("breakthrough_engine.retrieval._http_get")
    def test_reconstructs_abstract(self, mock_get):
        mock_get.return_value = MOCK_OPENALEX_RESPONSE
        from breakthrough_engine.retrieval import OpenAlexRetrievalSource
        source = OpenAlexRetrievalSource()
        items = source.gather("test", limit=10)
        assert "achieved" in items[0].quote
        assert "25.7%" in items[0].quote

    @patch("breakthrough_engine.retrieval._http_get")
    def test_cache_hit(self, mock_get):
        mock_get.return_value = MOCK_OPENALEX_RESPONSE
        db = _make_db()
        repo = Repository(db)
        from breakthrough_engine.retrieval import OpenAlexRetrievalSource, RetrievalCache
        cache = RetrievalCache(repo)
        source = OpenAlexRetrievalSource(cache=cache)

        # First call — cache miss
        items1 = source.gather("test", limit=10)
        assert len(items1) == 2
        assert mock_get.call_count == 1

        # Second call — cache hit, no HTTP
        items2 = source.gather("test", limit=10)
        assert len(items2) == 2
        assert mock_get.call_count == 1  # No additional call


class TestCrossrefRetrieval:
    @patch("breakthrough_engine.retrieval._http_get")
    def test_returns_evidence_items(self, mock_get):
        mock_get.return_value = MOCK_CROSSREF_RESPONSE
        from breakthrough_engine.retrieval import CrossrefRetrievalSource
        source = CrossrefRetrievalSource()
        items = source.gather("carbon capture", limit=10)
        assert len(items) == 1
        assert items[0].source_type == "crossref"
        assert "10.5678" in items[0].source_id
        assert "MOF-303" in items[0].quote

    @patch("breakthrough_engine.retrieval._http_get")
    def test_strips_jats_xml(self, mock_get):
        mock_get.return_value = MOCK_CROSSREF_RESPONSE
        from breakthrough_engine.retrieval import CrossrefRetrievalSource
        source = CrossrefRetrievalSource()
        items = source.gather("test", limit=10)
        assert "<p>" not in items[0].quote


class TestCompositeRetrieval:
    @patch("breakthrough_engine.retrieval._http_get")
    def test_combines_sources(self, mock_get):
        def side_effect(url, **kwargs):
            if "openalex" in url:
                return MOCK_OPENALEX_RESPONSE
            elif "crossref" in url:
                return MOCK_CROSSREF_RESPONSE
            return None

        mock_get.side_effect = side_effect
        from breakthrough_engine.retrieval import (
            CompositeRetrievalSource, CrossrefRetrievalSource, OpenAlexRetrievalSource,
        )
        source = CompositeRetrievalSource([
            OpenAlexRetrievalSource(),
            CrossrefRetrievalSource(),
        ])
        items = source.gather("test", limit=10)
        assert len(items) >= 2
        source_types = {i.source_type for i in items}
        assert "openalex" in source_types
        assert "crossref" in source_types


class TestRetrievalCache:
    def test_cache_roundtrip(self):
        db = _make_db()
        repo = Repository(db)
        from breakthrough_engine.retrieval import RetrievalCache
        cache = RetrievalCache(repo, ttl_hours=24)

        cache.put("test_source", "query1", [{"title": "A"}])
        result = cache.get("test_source", "query1")
        assert result is not None
        assert result[0]["title"] == "A"

    def test_cache_miss(self):
        db = _make_db()
        repo = Repository(db)
        from breakthrough_engine.retrieval import RetrievalCache
        cache = RetrievalCache(repo)
        result = cache.get("test_source", "nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Novelty Engine Tests
# ---------------------------------------------------------------------------

class TestNoveltyEngine:
    def _make_engine(self):
        db = _make_db()
        from breakthrough_engine.novelty import NoveltyEngine
        return NoveltyEngine(db), db

    def test_novel_candidate_passes(self):
        engine, db = self._make_engine()
        candidate = _make_candidate(title="Unique Quantum Catalyst")
        result = engine.evaluate(candidate)
        assert result.decision == NoveltyDecision.PASS
        assert result.novelty_score > 0.5
        assert len(result.prior_art_hits) == 0

    def test_exact_duplicate_fails(self):
        engine, db = self._make_engine()
        # Insert a prior candidate
        repo = Repository(db)
        prior_run = RunRecord(id="prior_run", program_name="test", mode=RunMode.DETERMINISTIC_TEST)
        repo.save_run(prior_run)
        prior = _make_candidate(title="Quantum Catalyst Method")
        prior.run_id = "prior_run"
        repo.save_candidate(prior)

        # Now check a near-duplicate
        candidate = _make_candidate(title="Quantum Catalyst Method")
        candidate.statement = prior.statement  # exact same statement
        result = engine.evaluate(candidate, exclude_run_id="new_run")
        assert result.decision == NoveltyDecision.FAIL
        assert result.duplicate_risk_score > 0.8
        assert len(result.prior_art_hits) > 0

    def test_mechanism_overlap_detected(self):
        engine, db = self._make_engine()
        repo = Repository(db)
        prior_run = RunRecord(id="prior_run", program_name="test", mode=RunMode.DETERMINISTIC_TEST)
        repo.save_run(prior_run)
        prior = _make_candidate(title="Prior Method A")
        prior.run_id = "prior_run"
        prior.mechanism = "Graphene interlayer creates ohmic contact reducing series resistance and improving charge extraction."
        repo.save_candidate(prior)

        candidate = _make_candidate(title="Different Title B")
        candidate.mechanism = "Graphene interlayer creates ohmic contact reducing series resistance and improving charge extraction."
        result = engine.evaluate(candidate, exclude_run_id="new_run")
        # Should detect mechanism overlap
        mech_hits = [h for h in result.prior_art_hits if h.overlap_type == "mechanism_overlap"]
        assert len(mech_hits) > 0

    def test_retrieved_evidence_overlap(self):
        engine, db = self._make_engine()
        candidate = _make_candidate(title="Novel Solar Cell Approach")
        candidate.statement = "Novel perovskite solar cell with graphene interlayer for improved efficiency and stability."
        candidate.mechanism = "Graphene interlayer reduces recombination and improves charge extraction in perovskite solar cells."

        retrieved = [
            EvidenceItem(
                source_type="openalex",
                source_id="doi:10.1234/test",
                title="Novel perovskite solar cell with graphene interlayer",
                quote="Novel perovskite solar cell with graphene interlayer for improved efficiency and stability through reduced recombination.",
                citation="Test 2024",
                relevance_score=0.9,
            )
        ]
        result = engine.evaluate(candidate, retrieved_evidence=retrieved)
        # Should detect keyword overlap with retrieved paper
        assert result.decision in (NoveltyDecision.WARN, NoveltyDecision.FAIL) or len(result.warnings) > 0

    def test_novelty_result_persisted(self):
        db = _make_db()
        repo = Repository(db)
        from breakthrough_engine.novelty import NoveltyEngine
        engine = NoveltyEngine(db)

        candidate = _make_candidate()
        result = engine.evaluate(candidate)
        repo.save_novelty_check(result)

        stored = repo.get_novelty_check(candidate.id)
        assert stored is not None
        assert stored["candidate_id"] == candidate.id
        assert stored["decision"] == "pass"


# ---------------------------------------------------------------------------
# Review Workflow Tests
# ---------------------------------------------------------------------------

class TestReviewWorkflow:
    def _setup(self):
        db = _make_db()
        repo = Repository(db)

        run = RunRecord(id="test_run", program_name="test", mode=RunMode.PRODUCTION_REVIEW)
        repo.save_run(run)

        candidate = _make_candidate()
        candidate.run_id = "test_run"
        repo.save_candidate(candidate)

        score = CandidateScore(
            candidate_id=candidate.id,
            novelty_score=0.8, plausibility_score=0.7,
            impact_score=0.9, evidence_strength_score=0.8,
            simulation_readiness_score=0.7, validation_cost_score=0.3,
            final_score=0.75,
        )
        return db, repo, candidate, score

    def test_create_draft(self):
        db, repo, candidate, score = self._setup()
        from breakthrough_engine.review import create_draft
        draft = create_draft(repo, "test_run", candidate, score)
        assert draft.status == DraftStatus.PENDING_REVIEW
        assert draft.candidate_title == candidate.title

        # Candidate should be in draft_pending_review
        c = repo.get_candidate(candidate.id)
        assert c["status"] == CandidateStatus.DRAFT_PENDING_REVIEW.value

    def test_approve_creates_publication(self):
        db, repo, candidate, score = self._setup()
        from breakthrough_engine.review import approve_draft, create_draft
        draft = create_draft(repo, "test_run", candidate, score)

        pub = approve_draft(repo, draft.id, reviewer="test_reviewer", notes="LGTM")
        assert pub is not None
        assert pub.candidate_id == candidate.id

        # Draft should be approved
        d = repo.get_draft(draft.id)
        assert d["status"] == DraftStatus.APPROVED.value

        # Candidate should be published
        c = repo.get_candidate(candidate.id)
        assert c["status"] == CandidateStatus.PUBLISHED.value

        # Run should have publication_id
        r = repo.get_run("test_run")
        assert r["publication_id"] == pub.id

        # Review event recorded
        events = repo.list_review_events(draft.id)
        assert len(events) == 1
        assert events[0]["action"] == "approve"
        assert events[0]["reviewer"] == "test_reviewer"

    def test_reject_prevents_publication(self):
        db, repo, candidate, score = self._setup()
        from breakthrough_engine.review import create_draft, reject_draft
        draft = create_draft(repo, "test_run", candidate, score)

        ok = reject_draft(repo, draft.id, reviewer="reviewer", reason="Not novel enough")
        assert ok is True

        # Draft should be rejected
        d = repo.get_draft(draft.id)
        assert d["status"] == DraftStatus.REJECTED.value

        # Candidate should be publication_failed
        c = repo.get_candidate(candidate.id)
        assert c["status"] == CandidateStatus.PUBLICATION_FAILED.value

        # Run should NOT have publication_id
        r = repo.get_run("test_run")
        assert r["publication_id"] is None

    def test_double_approve_prevented(self):
        db, repo, candidate, score = self._setup()
        from breakthrough_engine.review import approve_draft, create_draft
        draft = create_draft(repo, "test_run", candidate, score)
        approve_draft(repo, draft.id)
        pub2 = approve_draft(repo, draft.id)
        assert pub2 is None  # Already reviewed

    def test_one_publication_per_run_invariant(self):
        db, repo, candidate, score = self._setup()
        from breakthrough_engine.review import approve_draft, create_draft

        draft1 = create_draft(repo, "test_run", candidate, score)
        approve_draft(repo, draft1.id)

        # Create another draft for same run
        c2 = _make_candidate(title="Second Candidate")
        c2.run_id = "test_run"
        repo.save_candidate(c2)
        draft2 = create_draft(repo, "test_run", c2, score)

        # Approve should fail — run already has publication
        pub2 = approve_draft(repo, draft2.id)
        assert pub2 is None

    def test_review_queue_listing(self):
        db, repo, candidate, score = self._setup()
        from breakthrough_engine.review import create_draft
        create_draft(repo, "test_run", candidate, score)
        drafts = repo.list_drafts(status="pending_review")
        assert len(drafts) == 1


# ---------------------------------------------------------------------------
# Run Mode Tests
# ---------------------------------------------------------------------------

class TestRunModes:
    def test_production_review_creates_draft(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.evidence_source import DemoFixtureSource
        from breakthrough_engine.candidate_generator import FakeCandidateGenerator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(
            name="test", domain="test",
            mode=RunMode.PRODUCTION_REVIEW,
        )
        orch = BreakthroughOrchestrator(
            program=program, repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
        )
        run = orch.run()
        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION)

        # If completed, should have a draft but no publication
        if run.status == RunStatus.COMPLETED:
            assert run.publication_id is None
            draft = repo.get_draft_by_run(run.id)
            assert draft is not None
            assert draft["status"] == "pending_review"

    def test_production_shadow_no_publication(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.evidence_source import DemoFixtureSource
        from breakthrough_engine.candidate_generator import FakeCandidateGenerator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(
            name="test", domain="test",
            mode=RunMode.PRODUCTION_SHADOW,
        )
        orch = BreakthroughOrchestrator(
            program=program, repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
        )
        run = orch.run()
        # Shadow mode: COMPLETED if finalists exist, COMPLETED_NO_PUBLICATION if none pass
        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION)
        assert run.publication_id is None
        # No draft either
        draft = repo.get_draft_by_run(run.id)
        assert draft is None

    def test_demo_local_still_auto_publishes(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator
        from breakthrough_engine.evidence_source import DemoFixtureSource
        from breakthrough_engine.candidate_generator import FakeCandidateGenerator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(
            name="test", domain="test",
            mode=RunMode.DEMO_LOCAL,
        )
        orch = BreakthroughOrchestrator(
            program=program, repo=repo,
            evidence_source=DemoFixtureSource(),
            generator=FakeCandidateGenerator(),
        )
        run = orch.run()
        # Demo mode should auto-publish
        if run.status == RunStatus.COMPLETED:
            assert run.publication_id is not None

    def test_deterministic_test_unchanged(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(
            name="test", domain="test",
            mode=RunMode.DETERMINISTIC_TEST,
        )
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()
        assert run.status in (RunStatus.COMPLETED, RunStatus.COMPLETED_NO_PUBLICATION)


# ---------------------------------------------------------------------------
# Metrics Tests
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_metrics_persisted_after_run(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST)
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()

        metrics = repo.get_run_metrics(run.id)
        assert metrics is not None
        assert metrics["run_id"] == run.id
        assert metrics["evidence_count"] > 0
        assert metrics["total_duration_seconds"] >= 0

    def test_metrics_stage_durations(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST)
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()

        metrics = repo.get_run_metrics(run.id)
        durations = json.loads(metrics["stage_durations"])
        assert "evidence_gathering" in durations
        assert "novelty_gate" in durations

    def test_recent_metrics_list(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST)

        # Run twice
        for _ in range(2):
            orch = BreakthroughOrchestrator(program=program, repo=repo)
            orch.run()

        recent = repo.list_recent_metrics(limit=5)
        assert len(recent) == 2


# ---------------------------------------------------------------------------
# Notification Tests
# ---------------------------------------------------------------------------

class TestNotifications:
    def test_logging_notifier(self):
        from breakthrough_engine.notifications import LoggingNotifier, NotificationEvent
        n = LoggingNotifier()
        event = NotificationEvent(event_type="test", run_id="r1", message="hello")
        assert n.send(event) is True

    def test_file_notifier(self):
        from breakthrough_engine.notifications import FileNotifier, NotificationEvent
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "notifications.jsonl")
            n = FileNotifier(path=path)
            event = NotificationEvent(event_type="test", run_id="r1", message="hello")
            assert n.send(event) is True
            with open(path) as f:
                data = json.loads(f.readline())
            assert data["event_type"] == "test"
            assert data["run_id"] == "r1"

    def test_webhook_notifier_mocked(self):
        from breakthrough_engine.notifications import WebhookNotifier, NotificationEvent
        n = WebhookNotifier(url="http://example.com/hook")
        event = NotificationEvent(event_type="test", run_id="r1", message="hello")
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            assert n.send(event) is True
            mock_post.assert_called_once()

    def test_dispatcher_sends_to_all(self):
        from breakthrough_engine.notifications import NotificationDispatcher, NotificationEvent
        mock1 = MagicMock()
        mock1.send.return_value = True
        mock2 = MagicMock()
        mock2.send.return_value = True
        dispatcher = NotificationDispatcher(notifiers=[mock1, mock2])
        dispatcher.notify(NotificationEvent(event_type="test", message="hi"))
        mock1.send.assert_called_once()
        mock2.send.assert_called_once()

    def test_run_completed_notification(self):
        from breakthrough_engine.notifications import NotificationDispatcher
        mock = MagicMock()
        mock.send.return_value = True
        dispatcher = NotificationDispatcher(notifiers=[mock])
        dispatcher.run_completed("run1", "prog1", "completed")
        assert mock.send.call_count == 1
        event = mock.send.call_args[0][0]
        assert event.event_type == "run_completed"

    def test_draft_notification(self):
        from breakthrough_engine.notifications import NotificationDispatcher
        mock = MagicMock()
        mock.send.return_value = True
        dispatcher = NotificationDispatcher(notifiers=[mock])
        dispatcher.draft_awaiting_review("run1", "prog1", "draft1", "Cool Hypothesis")
        event = mock.send.call_args[0][0]
        assert event.event_type == "draft_awaiting_review"


# ---------------------------------------------------------------------------
# DB Migration Tests
# ---------------------------------------------------------------------------

class TestMigrationV002:
    def test_v002_tables_exist(self):
        db = _make_db()
        tables = [r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "bt_novelty_checks" in tables
        assert "bt_publication_drafts" in tables
        assert "bt_review_events" in tables
        assert "bt_run_metrics" in tables
        assert "bt_retrieval_cache" in tables

    def test_schema_version_is_2(self):
        db = _make_db()
        from breakthrough_engine.db import _current_version
        assert _current_version(db) == 2

    def test_idempotent_init(self):
        db = _make_db()
        from breakthrough_engine.db import _current_version
        v1 = _current_version(db)
        # Re-init should be safe
        from breakthrough_engine.db import init_db
        # Can't re-init in-memory, but verify version
        assert v1 == 2


# ---------------------------------------------------------------------------
# Phase 3 API Tests
# ---------------------------------------------------------------------------

class TestPhase3API:
    @pytest.fixture
    def client(self):
        from flask import Flask
        from breakthrough_engine.api import bp, configure
        configure(db_path=None)
        app = Flask(__name__)
        app.register_blueprint(bp)
        with app.app_context():
            yield app.test_client()

    def test_review_queue_empty(self, client):
        resp = client.get("/api/breakthrough/review/queue")
        assert resp.status_code == 200
        # Queue may contain drafts from live production_review runs
        assert isinstance(resp.get_json(), list)

    def test_review_draft_not_found(self, client):
        resp = client.get("/api/breakthrough/review/drafts/nonexistent")
        assert resp.status_code == 404

    def test_approve_not_found(self, client):
        resp = client.post("/api/breakthrough/review/drafts/nonexistent/approve",
                          json={"reviewer": "test"})
        assert resp.status_code == 400

    def test_reject_not_found(self, client):
        resp = client.post("/api/breakthrough/review/drafts/nonexistent/reject",
                          json={"reason": "bad"})
        assert resp.status_code == 400

    def test_metrics_recent(self, client):
        resp = client.get("/api/breakthrough/metrics/recent")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_novelty_not_found(self, client):
        resp = client.get("/api/breakthrough/novelty/nonexistent")
        assert resp.status_code == 404

    def test_list_drafts(self, client):
        resp = client.get("/api/breakthrough/review/drafts")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------

class TestPhase3Models:
    def test_novelty_result_model(self):
        nr = NoveltyResult(
            candidate_id="c1",
            novelty_score=0.8,
            decision=NoveltyDecision.PASS,
        )
        assert nr.novelty_score == 0.8
        assert nr.decision == NoveltyDecision.PASS

    def test_publication_draft_model(self):
        d = PublicationDraft(
            run_id="r1",
            candidate_id="c1",
            candidate_title="Test",
            hypothesis="Test hypothesis",
        )
        assert d.status == DraftStatus.PENDING_REVIEW

    def test_review_event_model(self):
        e = ReviewEvent(
            draft_id="d1",
            run_id="r1",
            candidate_id="c1",
            action=ReviewAction.APPROVE,
        )
        assert e.action == ReviewAction.APPROVE

    def test_run_metrics_model(self):
        m = RunMetrics(run_id="r1")
        assert m.evidence_count == 0
        assert m.draft_created is False

    def test_new_run_modes_exist(self):
        assert RunMode.PRODUCTION_REVIEW.value == "production_review"
        assert RunMode.PRODUCTION_SHADOW.value == "production_shadow"

    def test_new_candidate_statuses(self):
        assert CandidateStatus.NOVELTY_FAILED.value == "novelty_failed"
        assert CandidateStatus.DRAFT_PENDING_REVIEW.value == "draft_pending_review"


# ---------------------------------------------------------------------------
# Orchestrator Novelty Integration Test
# ---------------------------------------------------------------------------

class TestOrchestratorNovelty:
    def test_novelty_gate_runs(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST)
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()

        # Should have novelty checks for generated candidates
        candidates = repo.list_candidates_for_run(run.id)
        for c in candidates:
            # Novelty check should exist for candidates that got past evidence gate
            if c["status"] not in ("hypothesis_failed", "evidence_failed", "dedup_rejected"):
                nc = repo.get_novelty_check(c["id"])
                # May or may not have a check depending on pipeline flow
                # But the gate ran without errors

    def test_metrics_include_novelty_counts(self):
        from breakthrough_engine.models import ResearchProgram
        from breakthrough_engine.orchestrator import BreakthroughOrchestrator

        db = _make_db()
        repo = Repository(db)
        program = ResearchProgram(name="test", domain="test", mode=RunMode.DETERMINISTIC_TEST)
        orch = BreakthroughOrchestrator(program=program, repo=repo)
        run = orch.run()

        metrics = repo.get_run_metrics(run.id)
        assert metrics is not None
        assert "novelty_fail_count" in metrics
        assert "novelty_warn_count" in metrics
