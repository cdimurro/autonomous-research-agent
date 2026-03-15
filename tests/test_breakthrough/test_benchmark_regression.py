"""CC-BE-2425: Benchmark regression discipline for PV and battery domains.

These tests formalize PV and battery as regression-grade benchmark domains.
They validate:
- Unified report schema compliance
- Cross-domain report shape consistency
- Selectivity bounds (not all promoted, not all rejected at default threshold)
- Realism check presence and correctness
- Determinism with fixed seed
- Benchmark metadata consistency
"""

from __future__ import annotations

import json

import pytest

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.domain_models import (
    BENCHMARK_REPORT_REQUIRED_KEYS,
    BENCHMARK_REPORT_VERSION,
)
from breakthrough_engine.pv_loop import run_pv_benchmark
from breakthrough_engine.battery_loop import run_battery_benchmark


@pytest.fixture
def pv_repo():
    return Repository(init_db(in_memory=True))


@pytest.fixture
def battery_repo():
    return Repository(init_db(in_memory=True))


# ---------------------------------------------------------------------------
# Unified report schema compliance
# ---------------------------------------------------------------------------

class TestUnifiedReportSchema:
    """Both domains must emit reports conforming to the shared schema."""

    def test_pv_has_all_required_keys(self, pv_repo):
        report = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        missing = BENCHMARK_REPORT_REQUIRED_KEYS - set(report.keys())
        assert not missing, f"PV report missing keys: {missing}"

    def test_battery_has_all_required_keys(self, battery_repo):
        report = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        missing = BENCHMARK_REPORT_REQUIRED_KEYS - set(report.keys())
        assert not missing, f"Battery report missing keys: {missing}"

    def test_pv_version_matches(self, pv_repo):
        report = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        assert report["benchmark_version"] == BENCHMARK_REPORT_VERSION

    def test_battery_version_matches(self, battery_repo):
        report = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        assert report["benchmark_version"] == BENCHMARK_REPORT_VERSION


# ---------------------------------------------------------------------------
# Cross-domain report shape consistency
# ---------------------------------------------------------------------------

class TestCrossDomainConsistency:
    """PV and battery benchmark reports should have the same outer shape."""

    def test_same_top_level_required_keys(self, pv_repo, battery_repo):
        pv = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        bat = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        pv_keys = set(pv.keys()) & BENCHMARK_REPORT_REQUIRED_KEYS
        bat_keys = set(bat.keys()) & BENCHMARK_REPORT_REQUIRED_KEYS
        assert pv_keys == bat_keys

    def test_baseline_candidate_shape(self, pv_repo, battery_repo):
        pv = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        bat = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        assert "params" in pv["baseline_candidate"]
        assert "baseline_metrics" in pv["baseline_candidate"]
        assert "params" in bat["baseline_candidate"]
        assert "baseline_metrics" in bat["baseline_candidate"]

    def test_best_candidate_shape_when_promoted(self, pv_repo, battery_repo):
        pv = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        bat = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        for report in [pv, bat]:
            if report["best_candidate"]:
                bc = report["best_candidate"]
                assert "title" in bc
                assert "score" in bc
                assert "metrics" in bc
                assert "family" in bc
                assert "score_components" in bc

    def test_candidate_breakdown_entries(self, pv_repo, battery_repo):
        pv = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        bat = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        for report in [pv, bat]:
            for entry in report["candidate_breakdown"]:
                assert "title" in entry
                assert "score" in entry
                assert "decision" in entry
                assert "hard_fail" in entry

    def test_reference_comparison_shape(self, pv_repo, battery_repo):
        pv = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        bat = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        for report in [pv, bat]:
            ref = report["reference_comparison"]
            assert "reference_name" in ref
            assert "reference_metrics" in ref

    def test_summary_shape(self, pv_repo, battery_repo):
        pv = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        bat = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        required_summary_keys = {"run_id", "total_candidates", "promoted", "rejected", "hard_fail"}
        for report in [pv, bat]:
            missing = required_summary_keys - set(report["summary"].keys())
            assert not missing, f"Summary missing keys: {missing}"


# ---------------------------------------------------------------------------
# Selectivity bounds
# ---------------------------------------------------------------------------

class TestSelectivityBounds:
    """Benchmark domains should show selective behavior at default threshold."""

    def test_pv_not_all_promoted(self, pv_repo):
        """At default threshold, PV should not promote every candidate."""
        report = run_pv_benchmark(pv_repo, n_candidates=6, seed=42)
        total = report["summary"]["total_candidates"]
        promoted = report["summary"]["promoted"]
        assert promoted < total, "All PV candidates promoted — selectivity failure"

    def test_battery_not_all_promoted(self, battery_repo):
        """At default threshold, battery should not promote every candidate."""
        report = run_battery_benchmark(battery_repo, n_candidates=6, seed=42)
        total = report["summary"]["total_candidates"]
        promoted = report["summary"]["promoted"]
        assert promoted < total, "All battery candidates promoted — selectivity failure"

    def test_pv_high_threshold_rejects_all(self, pv_repo):
        """Very high threshold should result in no promotions."""
        report = run_pv_benchmark(pv_repo, n_candidates=4, seed=42, promotion_threshold=0.99)
        assert report["summary"]["promoted"] == 0

    def test_battery_high_threshold_rejects_all(self, battery_repo):
        """Very high threshold should result in no promotions."""
        report = run_battery_benchmark(battery_repo, n_candidates=3, seed=42, promotion_threshold=0.99)
        assert report["summary"]["promoted"] == 0

    def test_pv_breakdown_count_matches_n_candidates(self, pv_repo):
        report = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        assert len(report["candidate_breakdown"]) == 4

    def test_battery_breakdown_count_matches_n_candidates(self, battery_repo):
        report = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        assert len(report["candidate_breakdown"]) == 3


# ---------------------------------------------------------------------------
# Realism check assertions
# ---------------------------------------------------------------------------

class TestRealismChecks:
    """Reference/realism checks must be present and reasonable."""

    def test_pv_reference_produces_valid_metrics(self, pv_repo):
        report = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        ref = report["reference_comparison"]
        ref_m = ref["reference_metrics"]
        assert ref_m["Pmax"] > 0, "Reference Pmax must be positive"
        assert 0 < ref_m["fill_factor"] <= 1.0, "Reference FF must be 0–1"
        assert 0 < ref_m["efficiency"] < 33.7, "Reference efficiency must be below SQ limit"

    def test_battery_reference_produces_valid_metrics(self, battery_repo):
        report = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        ref = report["reference_comparison"]
        ref_m = ref["reference_metrics"]
        assert ref_m["discharge_capacity"] > 0, "Reference capacity must be positive"
        assert ref_m["coulombic_efficiency"] > 90, "Reference CE must be > 90%"

    def test_pv_reference_envelope_check_exists(self, pv_repo):
        report = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        if report["promotion_decision"] == "promoted":
            assert "within_reference_envelope" in report["reference_comparison"]

    def test_battery_reference_envelope_check_exists(self, battery_repo):
        report = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        if report["promotion_decision"] == "promoted":
            assert "within_reference_envelope" in report["reference_comparison"]


# ---------------------------------------------------------------------------
# Determinism regression
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same seed must produce identical benchmark reports."""

    def test_pv_deterministic(self):
        r1 = run_pv_benchmark(Repository(init_db(in_memory=True)), n_candidates=4, seed=42)
        r2 = run_pv_benchmark(Repository(init_db(in_memory=True)), n_candidates=4, seed=42)
        assert r1["promotion_decision"] == r2["promotion_decision"]
        assert r1["summary"]["promoted"] == r2["summary"]["promoted"]
        assert r1["summary"]["hard_fail"] == r2["summary"]["hard_fail"]
        if r1["best_candidate"] and r2["best_candidate"]:
            assert r1["best_candidate"]["score"] == r2["best_candidate"]["score"]

    def test_battery_deterministic(self):
        r1 = run_battery_benchmark(Repository(init_db(in_memory=True)), n_candidates=3, seed=42)
        r2 = run_battery_benchmark(Repository(init_db(in_memory=True)), n_candidates=3, seed=42)
        assert r1["promotion_decision"] == r2["promotion_decision"]
        assert r1["summary"]["promoted"] == r2["summary"]["promoted"]
        assert r1["summary"]["hard_fail"] == r2["summary"]["hard_fail"]
        if r1["best_candidate"] and r2["best_candidate"]:
            assert r1["best_candidate"]["score"] == r2["best_candidate"]["score"]

    def test_pv_json_round_trip(self, pv_repo):
        report = run_pv_benchmark(pv_repo, n_candidates=4, seed=42)
        loaded = json.loads(json.dumps(report, default=str))
        assert loaded["benchmark_version"] == BENCHMARK_REPORT_VERSION
        assert loaded["benchmark_domain"] == "pv_iv"

    def test_battery_json_round_trip(self, battery_repo):
        report = run_battery_benchmark(battery_repo, n_candidates=3, seed=42)
        loaded = json.loads(json.dumps(report, default=str))
        assert loaded["benchmark_version"] == BENCHMARK_REPORT_VERSION
        assert loaded["benchmark_domain"] == "battery_ecm"
