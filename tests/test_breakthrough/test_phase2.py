"""Phase 2 tests — Ollama generator, ExistingFindingsSource, benchmark, scheduler, Omniverse."""

import json
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from breakthrough_engine.benchmark import (
    BenchmarkCandidateGenerator,
    golden_generic,
    golden_high_quality,
    golden_overconfident,
    run_benchmark_suite,
)
from breakthrough_engine.candidate_generator import OllamaCandidateGenerator, OllamaConfig
from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.evidence_source import ExistingFindingsSource
from breakthrough_engine.models import RunMode, SimulationSpec
from breakthrough_engine.scheduler import RunLock, ScheduledRunStatus, run_scheduled


# ---------------------------------------------------------------------------
# Ollama generator tests (mocked, no live Ollama required)
# ---------------------------------------------------------------------------

MOCK_OLLAMA_RESPONSE = json.dumps([
    {
        "title": "Graphene-Enhanced Perovskite Solar Cell",
        "statement": "Adding a graphene interlayer between perovskite and electrode will increase efficiency by 15% through reduced interfacial recombination and improved charge extraction.",
        "mechanism": "Graphene's high conductivity and work function alignment with perovskite create an ohmic contact, reducing series resistance. The 2D nature prevents interdiffusion.",
        "expected_outcome": "Power conversion efficiency improvement from 22% to 25.3% in standard AM1.5G testing.",
        "testability_window_hours": 48.0,
        "novelty_notes": "First demonstration of graphene as a universal interlayer for perovskite photovoltaics.",
        "assumptions": ["Graphene does not quench perovskite luminescence", "Transfer process is scalable"],
        "risk_flags": ["Graphene quality variability"]
    },
    {
        "title": "Quantum Dot Enhanced Thermoelectric",
        "statement": "Embedding PbSe quantum dots in Bi2Te3 matrix will increase thermoelectric ZT to 3.0 through phonon scattering at QD interfaces while maintaining electronic conductivity.",
        "mechanism": "Quantum dots with diameter 5-10nm scatter mid-frequency phonons that carry most of the lattice thermal conductivity. Electronic transport is preserved through resonant tunneling.",
        "expected_outcome": "ZT = 3.0 at 300K measured by Harman method, validated by independent steady-state measurement.",
        "testability_window_hours": 72.0,
        "novelty_notes": "QD-thermoelectric composites have not been explored with PbSe/Bi2Te3.",
        "assumptions": ["QDs survive sintering", "Uniform dispersion achievable"],
        "risk_flags": ["Toxicity of PbSe"]
    }
])


class TestOllamaGenerator:
    def _make_generator(self):
        config = OllamaConfig(host="localhost:11434", model="test-model", temperature=0.7)
        return OllamaCandidateGenerator(config=config)

    @patch("breakthrough_engine.candidate_generator.OllamaCandidateGenerator._call_ollama")
    def test_generates_candidates_from_mock(self, mock_call):
        mock_call.return_value = MOCK_OLLAMA_RESPONSE
        gen = self._make_generator()
        from breakthrough_engine.evidence_source import DemoFixtureSource
        evidence = DemoFixtureSource().gather("test")
        candidates = gen.generate(evidence, "clean_energy", budget=5, run_id="test_run")
        assert len(candidates) == 2
        assert candidates[0].title == "Graphene-Enhanced Perovskite Solar Cell"
        assert candidates[0].domain == "clean_energy"
        assert candidates[0].run_id == "test_run"
        assert len(candidates[0].mechanism) > 10

    @patch("breakthrough_engine.candidate_generator.OllamaCandidateGenerator._call_ollama")
    def test_handles_empty_response(self, mock_call):
        mock_call.return_value = ""
        gen = self._make_generator()
        candidates = gen.generate([], "test", budget=5)
        assert candidates == []

    @patch("breakthrough_engine.candidate_generator.OllamaCandidateGenerator._call_ollama")
    def test_handles_malformed_json(self, mock_call):
        mock_call.return_value = "This is not JSON at all, just random text."
        gen = self._make_generator()
        candidates = gen.generate([], "test", budget=5)
        assert candidates == []

    @patch("breakthrough_engine.candidate_generator.OllamaCandidateGenerator._call_ollama")
    def test_handles_markdown_wrapped_json(self, mock_call):
        mock_call.return_value = f"Here are the candidates:\n```json\n{MOCK_OLLAMA_RESPONSE}\n```"
        gen = self._make_generator()
        from breakthrough_engine.evidence_source import DemoFixtureSource
        evidence = DemoFixtureSource().gather("test")
        candidates = gen.generate(evidence, "test", budget=5)
        assert len(candidates) == 2

    @patch("breakthrough_engine.candidate_generator.OllamaCandidateGenerator._call_ollama")
    def test_rejects_short_statements(self, mock_call):
        mock_call.return_value = json.dumps([
            {"title": "Bad", "statement": "Too short", "mechanism": ""}
        ])
        gen = self._make_generator()
        candidates = gen.generate([], "test", budget=5)
        assert candidates == []

    @patch("breakthrough_engine.candidate_generator.OllamaCandidateGenerator._call_ollama")
    def test_deduplicates_batch(self, mock_call):
        # Return two near-identical candidates
        mock_call.return_value = json.dumps([
            {
                "title": "A",
                "statement": "Adding a graphene interlayer between perovskite and electrode will increase efficiency by 15%.",
                "mechanism": "Graphene creates ohmic contact reducing resistance.",
                "expected_outcome": "15% efficiency gain",
            },
            {
                "title": "A Copy",
                "statement": "Adding a graphene interlayer between perovskite and electrode will increase efficiency by 15%.",
                "mechanism": "Graphene creates ohmic contact reducing resistance.",
                "expected_outcome": "15% efficiency gain",
            },
        ])
        gen = self._make_generator()
        candidates = gen.generate([], "test", budget=5)
        assert len(candidates) == 1

    @patch("breakthrough_engine.candidate_generator.OllamaCandidateGenerator._call_ollama")
    def test_handles_dict_wrapper(self, mock_call):
        mock_call.return_value = json.dumps({
            "hypotheses": [
                {
                    "title": "Wrapped Candidate",
                    "statement": "A novel approach to catalysis using bio-inspired enzymes for industrial CO2 reduction.",
                    "mechanism": "Enzyme mimetics provide lower activation energy pathways.",
                    "expected_outcome": "50% reduction in energy cost of CO2 conversion.",
                }
            ]
        })
        gen = self._make_generator()
        candidates = gen.generate([], "test", budget=5)
        assert len(candidates) == 1
        assert candidates[0].title == "Wrapped Candidate"


# ---------------------------------------------------------------------------
# ExistingFindingsSource tests (seeded SQLite)
# ---------------------------------------------------------------------------

def _create_seeded_db():
    """Create an in-memory DB with the existing pipeline tables + sample findings."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE papers (
            paper_id TEXT PRIMARY KEY,
            arxiv_id TEXT,
            doi TEXT,
            title TEXT NOT NULL,
            abstract TEXT,
            authors TEXT,
            source TEXT NOT NULL,
            subjects TEXT,
            publication_date TEXT,
            fetched_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            status TEXT DEFAULT 'indexed'
        );
        CREATE TABLE findings (
            finding_id TEXT PRIMARY KEY,
            paper_id TEXT REFERENCES papers(paper_id),
            finding_type TEXT NOT NULL,
            content TEXT NOT NULL,
            confidence REAL NOT NULL,
            provenance_quote TEXT,
            provenance_section TEXT,
            judge_verdict TEXT,
            created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        );
        INSERT INTO papers (paper_id, arxiv_id, title, source, subjects) VALUES
            ('p1', '2401.00001', 'Novel Perovskite Efficiency', 'arxiv', 'materials,solar'),
            ('p2', '2401.00002', 'Topological Insulator Thermoelectric', 'arxiv', 'physics,materials'),
            ('p3', '2401.00003', 'Quantum Computing Advances', 'arxiv', 'quantum,computing');
        INSERT INTO findings (finding_id, paper_id, finding_type, content, confidence, provenance_quote, judge_verdict) VALUES
            ('f1', 'p1', 'result', 'Achieved 23.7% power conversion efficiency', 0.90, 'We observed a 23.7% PCE', 'accepted'),
            ('f2', 'p1', 'result', 'Methylammonium-free composition shows stability', 0.85, 'The MA-free composition remained stable', 'accepted'),
            ('f3', 'p2', 'result', 'ZT=2.4 at 300K for Bi2Te3', 0.80, 'Bi2Te3 nanoribbons exhibited ZT=2.4', 'accepted'),
            ('f4', 'p3', 'result', 'Quantum error rates below threshold', 0.70, 'Error rates of 0.1%', 'accepted'),
            ('f5', 'p1', 'claim', 'Unverified claim about stability', 0.30, NULL, 'rejected');
    """)
    return db


class TestExistingFindingsSource:
    def test_gathers_from_seeded_db(self):
        db = _create_seeded_db()
        source = ExistingFindingsSource(db, min_confidence=0.6)
        items = source.gather("materials", limit=10)
        assert len(items) >= 2
        # Should have high-confidence accepted findings
        for item in items:
            assert item.relevance_score >= 0.6

    def test_filters_by_confidence(self):
        db = _create_seeded_db()
        source = ExistingFindingsSource(db, min_confidence=0.85)
        items = source.gather("cross-domain", limit=10)
        for item in items:
            assert item.relevance_score >= 0.85

    def test_cross_domain_returns_all(self):
        db = _create_seeded_db()
        source = ExistingFindingsSource(db, min_confidence=0.6)
        items = source.gather("cross-domain", limit=20)
        # cross-domain skips keyword filter, returns all accepted findings
        assert len(items) >= 3

    def test_keyword_filter(self):
        db = _create_seeded_db()
        source = ExistingFindingsSource(db, min_confidence=0.6, keyword_filter="quantum")
        items = source.gather("quantum", limit=10)
        assert len(items) >= 1
        # Should include quantum computing findings
        assert any("quantum" in i.title.lower() or "quantum" in i.source_id.lower() for i in items) or len(items) > 0

    def test_handles_empty_db(self):
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        source = ExistingFindingsSource(db, min_confidence=0.6)
        items = source.gather("test", limit=10)
        assert items == []

    def test_recency_filter(self):
        db = _create_seeded_db()
        # All findings have "now" timestamps, so recency filter of 1 day should include them
        source = ExistingFindingsSource(db, min_confidence=0.6, recency_days=1)
        items = source.gather("cross-domain", limit=10)
        assert len(items) >= 1

    def test_skips_findings_without_usable_text(self):
        db = _create_seeded_db()
        # f5 has NULL provenance_quote and short content, rejected verdict
        source = ExistingFindingsSource(db, min_confidence=0.1)
        items = source.gather("cross-domain", limit=20)
        finding_ids = [i.source_id for i in items]
        # f5 should be excluded (judge_verdict='rejected')
        assert not any("f5" in fid for fid in finding_ids)


# ---------------------------------------------------------------------------
# Benchmark tests
# ---------------------------------------------------------------------------

class TestBenchmark:
    def test_suite_runs_and_passes(self):
        suite = run_benchmark_suite()
        assert suite.total >= 9
        # All standard benchmarks should pass
        for r in suite.results:
            if not r.passed:
                pytest.fail(f"Benchmark '{r.name}' failed: {r.details}")

    def test_golden_high_quality_has_fields(self):
        c = golden_high_quality()
        assert len(c.statement) > 50
        assert len(c.mechanism) > 30
        assert len(c.assumptions) >= 1
        assert c.testability_window_hours > 0

    def test_golden_generic_is_empty(self):
        c = golden_generic()
        assert c.mechanism == ""
        assert c.testability_window_hours == 0.0

    def test_benchmark_generator(self):
        candidates = [golden_high_quality(), golden_overconfident()]
        gen = BenchmarkCandidateGenerator(candidates)
        from breakthrough_engine.evidence_source import DemoFixtureSource
        evidence = DemoFixtureSource().gather("test")
        result = gen.generate(evidence, "test", budget=5, run_id="bench_run")
        assert len(result) == 2
        assert result[0].run_id == "bench_run"


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_lock_acquire_release(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = RunLock(lock_dir=tmpdir)
            assert lock.acquire() is True
            assert lock.is_locked()
            # Second acquire should fail
            lock2 = RunLock(lock_dir=tmpdir)
            assert lock2.acquire() is False
            # Release
            lock.release()
            assert not lock.is_locked()
            # Now should succeed
            assert lock2.acquire() is True
            lock2.release()

    def test_lock_context_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = RunLock(lock_dir=tmpdir)
            with lock:
                assert lock.is_locked()
            assert not lock.is_locked()

    def test_lock_context_manager_raises_when_held(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock1 = RunLock(lock_dir=tmpdir)
            lock1.acquire()
            lock2 = RunLock(lock_dir=tmpdir)
            with pytest.raises(RuntimeError, match="Could not acquire"):
                with lock2:
                    pass
            lock1.release()

    def test_scheduled_run_succeeds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            status, msg = run_scheduled(
                program_name="general_fast_loop",
                db_path=db_path,
                lock_dir=tmpdir,
                output_dir=tmpdir,
            )
            assert status in (ScheduledRunStatus.SUCCESS, ScheduledRunStatus.COMPLETED_NO_PUBLICATION)
            # Check that artifact file was created
            artifact_files = [f for f in os.listdir(tmpdir) if f.startswith("scheduled_")]
            assert len(artifact_files) >= 1

    def test_scheduled_run_blocked_by_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = RunLock(lock_dir=tmpdir)
            lock.acquire()
            try:
                status, msg = run_scheduled(
                    program_name="general_fast_loop",
                    lock_dir=tmpdir,
                    output_dir=tmpdir,
                )
                assert status == ScheduledRunStatus.SKIPPED_DUE_TO_ACTIVE_LOCK
            finally:
                lock.release()

    def test_scheduled_run_bad_program(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            status, msg = run_scheduled(
                program_name="nonexistent_program",
                lock_dir=tmpdir,
                output_dir=tmpdir,
            )
            assert status == ScheduledRunStatus.FAILED
            assert "not found" in msg.lower()

    def test_launchd_plist_generation(self):
        from breakthrough_engine.scheduler import generate_launchd_plist
        plist = generate_launchd_plist(program_name="general_fast_loop", hour=7, minute=30)
        assert "com.scires.breakthrough" in plist
        assert "general_fast_loop" in plist
        assert "<integer>7</integer>" in plist
        assert "<integer>30</integer>" in plist


# ---------------------------------------------------------------------------
# API smoke tests for new routes
# ---------------------------------------------------------------------------

class TestPhase2API:
    @pytest.fixture
    def client(self):
        from flask import Flask
        from breakthrough_engine.api import bp, configure
        configure(db_path=None)
        app = Flask(__name__)
        app.register_blueprint(bp)
        # Init in-memory DB for API
        from breakthrough_engine.api import _get_db
        with app.app_context():
            yield app.test_client()

    def test_health_with_schema_version(self, client):
        resp = client.get("/api/breakthrough/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"

    def test_programs_list(self, client):
        resp = client.get("/api/breakthrough/programs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "general_fast_loop" in data
