"""Smoke tests for the API blueprint."""

import json

import pytest
from flask import Flask

from breakthrough_engine.api import bp, configure, _get_db
from breakthrough_engine.candidate_generator import FakeCandidateGenerator
from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.evidence_source import DemoFixtureSource
from breakthrough_engine.models import ResearchProgram, RunMode
from breakthrough_engine.orchestrator import BreakthroughOrchestrator
from breakthrough_engine.simulator import MockSimulatorAdapter


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True

    # Use in-memory db via monkey-patching
    import breakthrough_engine.api as api_mod
    db = init_db(in_memory=True)
    api_mod._db = db

    app.register_blueprint(bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def seeded_client(app):
    """Client with one completed run."""
    import breakthrough_engine.api as api_mod
    db = api_mod._db
    repo = Repository(db)
    program = ResearchProgram(
        name="api_test", domain="test",
        candidate_budget=3, simulation_budget=2,
        publication_threshold=0.50,
        mode=RunMode.DETERMINISTIC_TEST,
    )
    orchestrator = BreakthroughOrchestrator(
        program=program, repo=repo,
        evidence_source=DemoFixtureSource(),
        generator=FakeCandidateGenerator(),
        simulator=MockSimulatorAdapter(),
    )
    orchestrator.run()
    return app.test_client()


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/api/breakthrough/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"


class TestRunsEndpoints:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/breakthrough/runs")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_runs_with_data(self, seeded_client):
        resp = seeded_client.get("/api/breakthrough/runs")
        assert resp.status_code == 200
        runs = resp.get_json()
        assert len(runs) >= 1

    def test_get_run_not_found(self, client):
        resp = client.get("/api/breakthrough/runs/nonexistent")
        assert resp.status_code == 404


class TestPublicationsEndpoints:
    def test_list_publications_empty(self, client):
        resp = client.get("/api/breakthrough/publications")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_list_publications_with_data(self, seeded_client):
        resp = seeded_client.get("/api/breakthrough/publications")
        assert resp.status_code == 200
        pubs = resp.get_json()
        # May or may not have publications depending on scoring
        assert isinstance(pubs, list)

    def test_get_publication_not_found(self, client):
        resp = client.get("/api/breakthrough/publications/nonexistent")
        assert resp.status_code == 404


class TestRejectionsEndpoint:
    def test_list_rejections(self, seeded_client):
        # Get a run ID first
        runs = seeded_client.get("/api/breakthrough/runs").get_json()
        if runs:
            run_id = runs[0]["id"]
            resp = seeded_client.get(f"/api/breakthrough/rejections/{run_id}")
            assert resp.status_code == 200
            assert isinstance(resp.get_json(), list)


class TestProgramsEndpoint:
    def test_list_programs(self, client):
        resp = client.get("/api/breakthrough/programs")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)


class TestHTMLViews:
    def test_view_latest_empty(self, client):
        resp = client.get("/api/breakthrough/view/latest")
        assert resp.status_code == 200
        assert b"No publications yet" in resp.data

    def test_view_runs(self, seeded_client):
        resp = seeded_client.get("/api/breakthrough/view/runs")
        assert resp.status_code == 200
        assert b"Breakthrough Engine" in resp.data

    def test_run_report_md(self, seeded_client):
        runs = seeded_client.get("/api/breakthrough/runs").get_json()
        if runs:
            run_id = runs[0]["id"]
            resp = seeded_client.get(f"/api/breakthrough/runs/{run_id}/report.md")
            assert resp.status_code == 200
            assert b"Breakthrough Run Report" in resp.data
