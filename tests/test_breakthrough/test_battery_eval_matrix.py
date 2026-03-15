"""Tests for the Battery V2 evaluation matrix."""

import json

import pytest

from breakthrough_engine.battery_eval_matrix import (
    EVAL_MODES,
    run_eval_matrix,
    run_single_mode,
    save_eval_matrix_artifact,
)
from breakthrough_engine.db import Repository, init_db


@pytest.fixture
def repo():
    return Repository(init_db(in_memory=True))


class TestEvalModes:
    def test_four_modes_defined(self):
        assert len(EVAL_MODES) == 4

    def test_mode_keys(self):
        assert "ecm_only" in EVAL_MODES
        assert "ecm_mock_sidecar" in EVAL_MODES
        assert "ecm_cathode" in EVAL_MODES
        assert "full_v2_mock" in EVAL_MODES

    def test_each_mode_has_description(self):
        for mode, cfg in EVAL_MODES.items():
            assert "description" in cfg
            assert len(cfg["description"]) > 0


class TestSingleModeRun:
    def test_ecm_only_runs(self, repo):
        result = run_single_mode(repo, "ecm_only", seed=42, n_candidates=3)
        assert result["mode"] == "ecm_only"
        assert result["seed"] == 42
        assert result["n_candidates"] == 3
        assert "promoted_count" in result
        assert "score_mean" in result

    def test_full_v2_mock_runs(self, repo):
        result = run_single_mode(repo, "full_v2_mock", seed=42, n_candidates=3)
        assert result["mode"] == "full_v2_mock"
        assert "sidecar_active" in result

    def test_result_has_required_keys(self, repo):
        result = run_single_mode(repo, "ecm_only", seed=42, n_candidates=3)
        required = {
            "mode", "seed", "n_candidates", "elapsed_seconds",
            "promoted_count", "rejected_count", "hard_fail_count",
            "promotion_rate", "score_mean", "score_max", "score_min",
            "unique_families", "unique_family_count",
            "sidecar_active", "sidecar_veto_count", "sidecar_caveat_count",
            "within_reference_envelope",
            "winner_title", "winner_score", "winner_family", "winner_is_cathode",
        }
        assert required.issubset(set(result.keys()))

    def test_deterministic_same_seed(self):
        repo1 = Repository(init_db(in_memory=True))
        repo2 = Repository(init_db(in_memory=True))
        r1 = run_single_mode(repo1, "ecm_only", seed=42, n_candidates=3)
        r2 = run_single_mode(repo2, "ecm_only", seed=42, n_candidates=3)
        assert r1["winner_score"] == r2["winner_score"]
        assert r1["promoted_count"] == r2["promoted_count"]


class TestEvalMatrix:
    def test_matrix_runs(self):
        matrix = run_eval_matrix(seeds=[42], modes=["ecm_only"], n_candidates=3)
        assert matrix["eval_matrix_version"] == 1
        assert matrix["total_runs"] == 1
        assert len(matrix["results"]) == 1

    def test_matrix_structure(self):
        matrix = run_eval_matrix(seeds=[42], modes=["ecm_only", "full_v2_mock"], n_candidates=3)
        assert matrix["total_runs"] == 2
        assert "comparison" in matrix
        assert "mode_stats" in matrix["comparison"]

    def test_comparison_has_mode_stats(self):
        matrix = run_eval_matrix(
            seeds=[42], modes=["ecm_only", "full_v2_mock"], n_candidates=3,
        )
        stats = matrix["comparison"]["mode_stats"]
        assert "ecm_only" in stats
        assert "full_v2_mock" in stats
        for mode_stat in stats.values():
            assert "mean_best_score" in mode_stat
            assert "mean_promotion_rate" in mode_stat

    def test_winner_change_detection(self):
        matrix = run_eval_matrix(
            seeds=[42], modes=["ecm_only", "ecm_cathode"], n_candidates=3,
        )
        comp = matrix["comparison"]
        assert "winner_changes" in comp
        assert "sidecar_changed_winner" in comp
        assert "cathode_changed_winner" in comp

    def test_results_exclude_full_report(self):
        matrix = run_eval_matrix(seeds=[42], modes=["ecm_only"], n_candidates=3)
        for r in matrix["results"]:
            assert "full_report" not in r

    def test_matrix_json_serializable(self):
        matrix = run_eval_matrix(seeds=[42], modes=["ecm_only"], n_candidates=3)
        serialized = json.dumps(matrix, default=str)
        assert isinstance(serialized, str)


class TestArtifactSave:
    def test_save_creates_file(self, tmp_path):
        matrix = run_eval_matrix(seeds=[42], modes=["ecm_only"], n_candidates=3)
        path = save_eval_matrix_artifact(matrix, output_dir=str(tmp_path))
        assert (tmp_path / "battery_eval_matrix.json").exists()
        loaded = json.loads((tmp_path / "battery_eval_matrix.json").read_text())
        assert loaded["eval_matrix_version"] == 1
