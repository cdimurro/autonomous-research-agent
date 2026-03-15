"""Tests for the Battery Decision Brief."""

import json

import pytest

from breakthrough_engine.battery_decision_brief import (
    BatteryDecisionBrief,
    generate_decision_brief,
    save_decision_brief,
)
from breakthrough_engine.battery_loop import run_battery_benchmark
from breakthrough_engine.battery_sidecar import MockPyBaMMSidecar
from breakthrough_engine.db import Repository, init_db


@pytest.fixture
def repo():
    return Repository(init_db(in_memory=True))


@pytest.fixture
def report_with_promotion(repo):
    return run_battery_benchmark(repo, n_candidates=6, seed=42)


@pytest.fixture
def report_with_sidecar(repo):
    sidecar = MockPyBaMMSidecar(seed=42)
    return run_battery_benchmark(repo, n_candidates=6, seed=42, sidecar=sidecar)


class TestBatteryDecisionBriefSchema:
    def test_schema_has_required_fields(self):
        brief = BatteryDecisionBrief(
            title="Test", headline="Test headline",
        )
        assert brief.title == "Test"
        assert brief.review_state == "awaiting_review"
        assert brief.confidence_tier == "standard"
        assert brief.sidecar_status == "not_verified"

    def test_schema_serializable(self):
        brief = BatteryDecisionBrief(title="Test", headline="test")
        d = brief.model_dump()
        serialized = json.dumps(d, default=str)
        assert isinstance(serialized, str)


class TestGenerateDecisionBrief:
    def test_generates_from_promoted_report(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if report_with_promotion["promotion_decision"] == "promoted":
            assert brief is not None
            assert len(brief.title) > 0
            assert len(brief.headline) > 0
            assert brief.final_score > 0

    def test_returns_none_when_no_promotion(self, repo):
        report = run_battery_benchmark(repo, n_candidates=3, seed=42, promotion_threshold=0.99)
        brief = generate_decision_brief(report)
        if report["promotion_decision"] == "none":
            assert brief is None

    def test_brief_has_key_changes(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert isinstance(brief.key_changes, list)

    def test_brief_has_score_summary(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert len(brief.score_summary) > 0
            assert brief.final_score > 0

    def test_brief_has_fast_charge_summary(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert isinstance(brief.fast_charge_summary, str)

    def test_brief_has_degradation_summary(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert isinstance(brief.degradation_summary, str)

    def test_brief_has_caveats(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert isinstance(brief.caveats, list)

    def test_brief_has_vs_alternatives(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert len(brief.vs_alternatives) > 0

    def test_brief_has_recommended_action(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert len(brief.recommended_action) > 0

    def test_brief_has_confidence_tier(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert brief.confidence_tier in ("high", "standard", "low", "unverified")

    def test_brief_preserves_machine_data(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            assert isinstance(brief.baseline_metrics, dict)
            assert isinstance(brief.candidate_metrics, dict)
            assert brief.benchmark_seed == 42


class TestSidecarBrief:
    def test_sidecar_status_populated(self, report_with_sidecar):
        brief = generate_decision_brief(report_with_sidecar)
        if brief:
            assert brief.sidecar_status in ("success", "not_verified")
            assert len(brief.sidecar_summary) > 0

    def test_sidecar_concordance_present(self, report_with_sidecar):
        brief = generate_decision_brief(report_with_sidecar)
        if brief and brief.sidecar_status == "success":
            assert brief.sidecar_concordance is not None

    def test_sidecar_gate_decision(self, report_with_sidecar):
        brief = generate_decision_brief(report_with_sidecar)
        if brief:
            assert brief.sidecar_gate_decision in (
                "confirmed", "caveat", "veto", "not_verified",
            )

    def test_sidecar_what_it_means_nonempty(self, report_with_sidecar):
        brief = generate_decision_brief(report_with_sidecar)
        if brief:
            assert len(brief.sidecar_what_it_means) > 0

    def test_no_sidecar_brief_has_ecm_only_meaning(self, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief and brief.sidecar_status == "not_verified":
            assert "ECM" in brief.sidecar_what_it_means

    def test_v2_schema_fields_present(self):
        brief = BatteryDecisionBrief(title="Test", headline="test")
        assert hasattr(brief, "sidecar_gate_decision")
        assert hasattr(brief, "sidecar_what_it_means")
        assert hasattr(brief, "sidecar_concordance_details")

    def test_v25_calibration_fields_present(self):
        brief = BatteryDecisionBrief(title="Test", headline="test")
        assert hasattr(brief, "sidecar_calibration_note")
        assert hasattr(brief, "sidecar_high_rate_agreement")

    def test_high_confidence_requires_high_concordance(self):
        """Confidence 'high' requires concordance >= 0.80 and score >= 0.65."""
        from breakthrough_engine.battery_decision_brief import _compute_confidence_tier
        assert _compute_confidence_tier(0.70, "success", 0.85, None) == "high"
        assert _compute_confidence_tier(0.70, "success", 0.65, None) == "standard"
        assert _compute_confidence_tier(0.50, "success", 0.90, None) == "low"

    def test_heuristic_caps_at_low(self):
        from breakthrough_engine.battery_decision_brief import _compute_confidence_tier
        assert _compute_confidence_tier(0.70, "success", 0.90, "heuristic") == "low"


class TestSaveBrief:
    def test_save_creates_file(self, tmp_path, report_with_promotion):
        brief = generate_decision_brief(report_with_promotion)
        if brief:
            path = save_decision_brief(brief, output_dir=str(tmp_path))
            assert (tmp_path / f"brief_{brief.id}.json").exists()
            loaded = json.loads((tmp_path / f"brief_{brief.id}.json").read_text())
            assert loaded["title"] == brief.title
