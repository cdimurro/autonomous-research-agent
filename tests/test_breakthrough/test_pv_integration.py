"""Integration tests for PV loop CLI and daily path (CC-BE-2405)."""

from __future__ import annotations

import json
import os

import pytest

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.pv_loop import PVOptimizationLoop


# ---------------------------------------------------------------------------
# CLI integration tests (via function, not subprocess)
# ---------------------------------------------------------------------------

class TestPVCLI:
    @pytest.fixture
    def db_repo(self):
        db = init_db(in_memory=True)
        return Repository(db)

    def test_pv_dry_run(self, db_repo, capsys):
        """pv dry-run should print candidates without running experiments."""
        from breakthrough_engine.pv_loop import generate_pv_candidates
        candidates = generate_pv_candidates(n_candidates=3, seed=42)
        assert len(candidates) == 3
        for c in candidates:
            assert c.domain_name == "pv_iv"
            assert c.title
            assert c.rationale

    def test_pv_run_produces_artifacts(self, db_repo, tmp_path):
        """pv run should produce result artifacts."""
        loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=42)
        result = loop.run(run_id="cli_test_1")
        summary = result.summary()

        # Write artifact like CLI does
        artifact_path = tmp_path / "pv_run_cli_test_1.json"
        with open(artifact_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        assert artifact_path.exists()
        with open(artifact_path) as f:
            loaded = json.load(f)
        assert loaded["total_candidates"] == 3
        assert loaded["baseline_pmax"] > 0

    def test_pv_status_after_run(self, db_repo):
        """After a run, status should show candidates and promotions."""
        loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="status_test")

        candidates = db_repo.list_domain_candidates("pv_iv")
        promos = db_repo.list_promotion_records("pv_iv")
        assert len(candidates) == 3
        assert len(promos) == 3

    def test_pv_memory_after_run(self, db_repo):
        """After a run, memory command should show accumulated lessons."""
        loop = PVOptimizationLoop(db_repo, n_candidates=4, seed=42)
        loop.run(run_id="mem_test")

        ideas = db_repo.list_idea_memory("pv_iv")
        exp_mem = db_repo.list_experiment_memory("pv_iv")
        assert len(ideas) == 4
        assert len(exp_mem) == 4
        for m in ideas:
            assert m["lesson"] != ""


# ---------------------------------------------------------------------------
# Research program config tests
# ---------------------------------------------------------------------------

class TestPVConfig:
    def test_pv_research_program_exists(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "config", "research_programs", "pv_iv.yaml",
        )
        # Normalize path
        config_path = os.path.normpath(config_path)
        assert os.path.exists(config_path), f"PV research program not found at {config_path}"

    def test_pv_daily_profile_exists(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "config", "daily_profiles", "pv_evaluation.yaml",
        )
        config_path = os.path.normpath(config_path)
        assert os.path.exists(config_path), f"PV daily profile not found at {config_path}"

    def test_pv_domain_config_exists(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "config", "domains", "pv_iv.yaml",
        )
        config_path = os.path.normpath(config_path)
        assert os.path.exists(config_path), f"PV domain config not found at {config_path}"


# ---------------------------------------------------------------------------
# Multi-run integration tests
# ---------------------------------------------------------------------------

class TestPVMultiRun:
    @pytest.fixture
    def db_repo(self):
        db = init_db(in_memory=True)
        return Repository(db)

    def test_three_sequential_runs(self, db_repo):
        """Three sequential runs should accumulate memory correctly."""
        for i in range(3):
            loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=i * 10 + 1)
            result = loop.run(run_id=f"multi_run_{i}")
            assert result.total_candidates == 3

        # Should have 9 candidates total
        candidates = db_repo.list_domain_candidates("pv_iv", limit=100)
        assert len(candidates) == 9

        # Should have 9 idea memories
        ideas = db_repo.list_idea_memory("pv_iv", limit=100)
        assert len(ideas) == 9

        # Should have 9 experiment memories
        exp_mem = db_repo.list_experiment_memory("pv_iv", limit=100)
        assert len(exp_mem) == 9

    def test_one_promotion_per_run(self, db_repo):
        """Each run should select at most one best promoted candidate."""
        results = []
        for i in range(3):
            loop = PVOptimizationLoop(db_repo, n_candidates=4, seed=i * 7, promotion_threshold=0.3)
            result = loop.run(run_id=f"promo_test_{i}")
            results.append(result)

        # Each run selects at most one best_promoted
        for r in results:
            # best_promoted is either None or exactly one
            assert r.best_promoted is None or isinstance(r.best_promoted.candidate.title, str)

    def test_artifacts_are_json_serializable(self, db_repo):
        """All loop results should be JSON-serializable."""
        loop = PVOptimizationLoop(db_repo, n_candidates=4, seed=42)
        result = loop.run(run_id="json_test")
        summary = result.summary()
        json_str = json.dumps(summary, default=str)
        loaded = json.loads(json_str)
        assert loaded["total_candidates"] == 4

    def test_existing_production_path_untouched(self, db_repo):
        """PV loop should not write to bt_candidates or bt_publications."""
        loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="isolation_test")

        # bt_candidates (broad-domain) should be empty
        broad_candidates = db_repo.db.execute(
            "SELECT COUNT(*) FROM bt_candidates"
        ).fetchone()[0]
        assert broad_candidates == 0

        # bt_publications should be empty
        pubs = db_repo.db.execute(
            "SELECT COUNT(*) FROM bt_publications"
        ).fetchone()[0]
        assert pubs == 0

        # bt_domain_candidates should have PV candidates
        pv_count = db_repo.db.execute(
            "SELECT COUNT(*) FROM bt_domain_candidates WHERE domain_name='pv_iv'"
        ).fetchone()[0]
        assert pv_count == 3
