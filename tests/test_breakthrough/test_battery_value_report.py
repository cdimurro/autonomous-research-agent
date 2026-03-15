"""Tests for the Battery architecture value report."""

import json

import pytest

from breakthrough_engine.battery_eval_matrix import run_eval_matrix
from breakthrough_engine.battery_value_report import (
    generate_value_report,
    save_value_report,
)


@pytest.fixture
def matrix():
    return run_eval_matrix(
        seeds=[42], modes=["ecm_only", "full_v2_mock"], n_candidates=3,
    )


class TestValueReport:
    def test_report_structure(self, matrix):
        report = generate_value_report(matrix)
        assert report["report_type"] == "battery_architecture_value_report"
        assert report["report_version"] == 1
        assert "sections" in report
        assert "recommendation" in report

    def test_required_sections(self, matrix):
        report = generate_value_report(matrix)
        sections = report["sections"]
        assert "score_comparison" in sections
        assert "sidecar_impact" in sections
        assert "cathode_family_impact" in sections
        assert "full_v2_vs_ecm" in sections
        assert "runtime_tradeoffs" in sections
        assert "winner_changes" in sections

    def test_score_comparison_has_modes(self, matrix):
        report = generate_value_report(matrix)
        sc = report["sections"]["score_comparison"]
        assert "ecm_only" in sc
        assert "full_v2_mock" in sc

    def test_sidecar_impact_has_assessment(self, matrix):
        report = generate_value_report(matrix)
        si = report["sections"]["sidecar_impact"]
        assert "assessment" in si
        assert isinstance(si["assessment"], str)
        assert len(si["assessment"]) > 0

    def test_full_v2_comparison(self, matrix):
        report = generate_value_report(matrix)
        fv = report["sections"]["full_v2_vs_ecm"]
        assert "ecm_mean_score" in fv
        assert "full_v2_mean_score" in fv
        assert "score_delta" in fv
        assert "assessment" in fv

    def test_recommendation_is_nonempty_string(self, matrix):
        report = generate_value_report(matrix)
        assert isinstance(report["recommendation"], str)
        assert len(report["recommendation"]) > 20

    def test_report_json_serializable(self, matrix):
        report = generate_value_report(matrix)
        serialized = json.dumps(report, default=str)
        assert isinstance(serialized, str)

    def test_four_mode_comparison(self):
        matrix = run_eval_matrix(
            seeds=[42],
            modes=["ecm_only", "ecm_mock_sidecar", "ecm_cathode", "full_v2_mock"],
            n_candidates=3,
        )
        report = generate_value_report(matrix)
        sc = report["sections"]["score_comparison"]
        assert len(sc) == 4


class TestSaveReport:
    def test_save_creates_file(self, tmp_path, matrix):
        report = generate_value_report(matrix)
        path = save_value_report(report, output_dir=str(tmp_path))
        assert (tmp_path / "battery_value_report.json").exists()
        loaded = json.loads((tmp_path / "battery_value_report.json").read_text())
        assert loaded["report_type"] == "battery_architecture_value_report"
