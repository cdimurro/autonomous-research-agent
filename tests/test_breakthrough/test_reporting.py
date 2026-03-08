"""Tests for report generation."""

import tempfile

from breakthrough_engine.candidate_generator import FakeCandidateGenerator
from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.evidence_source import DemoFixtureSource
from breakthrough_engine.models import ResearchProgram, RunMode
from breakthrough_engine.orchestrator import BreakthroughOrchestrator
from breakthrough_engine.reporting import (
    generate_json_report,
    generate_markdown_report,
    save_reports,
)
from breakthrough_engine.simulator import MockSimulatorAdapter


def _run_cycle():
    db = init_db(in_memory=True)
    repo = Repository(db)
    program = ResearchProgram(
        name="report_test", domain="test",
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
    run = orchestrator.run()
    return repo, run


def test_json_report_structure():
    repo, run = _run_cycle()
    report = generate_json_report(repo, run.id)
    assert "run" in report
    assert "summary" in report
    assert "publications" in report
    assert "rejections" in report
    assert "candidates" in report
    assert report["summary"]["candidates_generated"] == 3


def test_json_report_not_found():
    db = init_db(in_memory=True)
    repo = Repository(db)
    report = generate_json_report(repo, "nonexistent")
    assert "error" in report


def test_markdown_report_contains_key_sections():
    repo, run = _run_cycle()
    md = generate_markdown_report(repo, run.id)
    assert "# Breakthrough Run Report" in md
    assert "Run ID:" in md
    assert "Candidates generated:" in md


def test_save_reports_creates_files():
    repo, run = _run_cycle()
    with tempfile.TemporaryDirectory() as d:
        json_path, md_path = save_reports(repo, run.id, output_dir=d)
        assert json_path.endswith(".json")
        assert md_path.endswith(".md")
        with open(json_path) as f:
            import json
            data = json.load(f)
            assert "run" in data
