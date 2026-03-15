"""Tests for Battery optimization loop (CC-BE-2413 through CC-BE-2415)."""

from __future__ import annotations

import json

import pytest

from breakthrough_engine.battery_domain import DEFAULT_CELL_PARAMS, run_experiment
from breakthrough_engine.battery_loop import (
    BATTERY_SCORE_WEIGHTS,
    CANDIDATE_FAMILIES,
    PARAM_RANGES,
    PROPOSAL_TAG_EXPLORATORY,
    PROPOSAL_TAG_MEMORY,
    PROPOSAL_TAG_RECOVERY,
    PROPOSAL_TAG_RETRY,
    BatteryOptimizationLoop,
    _check_cross_parameter_plausibility,
    _compute_family_weights,
    compute_robustness_profile,
    generate_battery_candidates,
    generate_candidate_caveats,
    run_battery_benchmark,
    score_battery_candidate,
)
from breakthrough_engine.db import Repository, init_db


# ---------------------------------------------------------------------------
# CC-BE-2413: Candidate generation tests
# ---------------------------------------------------------------------------

class TestBatteryCandidateGeneration:
    def test_generates_correct_count(self):
        candidates = generate_battery_candidates(n_candidates=4, seed=42)
        assert len(candidates) == 4

    def test_all_candidates_have_battery_domain(self):
        candidates = generate_battery_candidates(n_candidates=6, seed=42)
        for c in candidates:
            assert c.domain_name == "battery_ecm"

    def test_all_candidates_have_titles(self):
        candidates = generate_battery_candidates(n_candidates=6, seed=42)
        for c in candidates:
            assert c.title
            assert "Battery" in c.title

    def test_all_candidates_have_rationale(self):
        candidates = generate_battery_candidates(n_candidates=6, seed=42)
        for c in candidates:
            assert c.rationale
            assert "[" in c.rationale  # Contains proposal tag

    def test_parameters_within_bounds(self):
        candidates = generate_battery_candidates(n_candidates=20, seed=42)
        for c in candidates:
            for param, (lo, hi) in PARAM_RANGES.items():
                if param in c.parameters:
                    val = c.parameters[param]
                    assert lo <= val <= hi, f"{param}={val} out of range [{lo}, {hi}]"

    def test_seed_reproducibility(self):
        c1 = generate_battery_candidates(n_candidates=4, seed=42)
        c2 = generate_battery_candidates(n_candidates=4, seed=42)
        for a, b in zip(c1, c2):
            assert a.title == b.title
            assert a.parameters == b.parameters

    def test_different_seeds_produce_different_candidates(self):
        c1 = generate_battery_candidates(n_candidates=4, seed=1)
        c2 = generate_battery_candidates(n_candidates=4, seed=2)
        # At least one candidate should differ
        assert any(a.parameters != b.parameters for a, b in zip(c1, c2))


class TestCrossParameterPlausibility:
    def test_default_params_pass(self):
        ok, reasons = _check_cross_parameter_plausibility(DEFAULT_CELL_PARAMS)
        assert ok is True

    def test_low_r0_high_fade_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, R0_mohm=10.0, fade_rate_per_cycle=0.004)
        ok, reasons = _check_cross_parameter_plausibility(params)
        assert ok is False
        assert any("R0" in r for r in reasons)

    def test_high_cap_low_efficiency_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, capacity_ah=5.5, coulombic_eff=0.96)
        ok, reasons = _check_cross_parameter_plausibility(params)
        assert ok is False

    def test_reasonable_combinations_pass(self):
        # Low R0 with low fade is fine
        params = dict(DEFAULT_CELL_PARAMS, R0_mohm=12.0, fade_rate_per_cycle=0.0002)
        ok, _ = _check_cross_parameter_plausibility(params)
        assert ok is True


class TestMemoryGuidedGeneration:
    def test_exploratory_tags_without_memory(self):
        candidates = generate_battery_candidates(n_candidates=4, seed=42)
        for c in candidates:
            assert PROPOSAL_TAG_EXPLORATORY in c.rationale

    def test_memory_supported_tags_with_promotions(self):
        lessons = [
            {"candidate_family": "reduced_resistance", "outcome": "promoted"},
            {"candidate_family": "reduced_resistance", "outcome": "promoted"},
        ]
        weights, tags = _compute_family_weights(lessons)
        assert tags["reduced_resistance"] == PROPOSAL_TAG_MEMORY
        assert weights["reduced_resistance"] > 1.0

    def test_retry_tags_for_hard_fails(self):
        lessons = [
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
        ]
        weights, tags = _compute_family_weights(lessons)
        assert tags["bounded_aggressive"] == PROPOSAL_TAG_RETRY
        assert weights["bounded_aggressive"] < 0.5

    def test_recovery_tags_for_all_rejected(self):
        lessons = [
            {"candidate_family": "improved_capacity", "outcome": "rejected"},
            {"candidate_family": "improved_capacity", "outcome": "rejected"},
        ]
        weights, tags = _compute_family_weights(lessons)
        assert tags["improved_capacity"] == PROPOSAL_TAG_RECOVERY
        assert weights["improved_capacity"] == 0.5

    def test_weighted_selection_favors_promoted_families(self):
        lessons = [
            {"candidate_family": "reduced_resistance", "outcome": "promoted"},
            {"candidate_family": "reduced_resistance", "outcome": "promoted"},
        ] + [
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
        ] * 5
        # Over many candidates, reduced_resistance should appear more often
        candidates = generate_battery_candidates(
            n_candidates=30, seed=42, prior_lessons=lessons,
        )
        rr_count = sum(1 for c in candidates if "reduced_resistance" in c.title)
        ba_count = sum(1 for c in candidates if "bounded_aggressive" in c.title)
        assert rr_count > ba_count


class TestCandidateFamilies:
    def test_all_families_defined(self):
        family_names = {f["family"] for f in CANDIDATE_FAMILIES}
        assert "reduced_resistance" in family_names
        assert "improved_capacity" in family_names
        assert "reduced_fade" in family_names
        assert "improved_efficiency" in family_names
        assert "combined_moderate" in family_names
        assert "bounded_aggressive" in family_names

    def test_all_families_have_rationale(self):
        for f in CANDIDATE_FAMILIES:
            assert f["rationale"]

    def test_all_families_have_perturbations(self):
        for f in CANDIDATE_FAMILIES:
            assert f["perturbations"]
            for param in f["perturbations"]:
                assert param in PARAM_RANGES or param in DEFAULT_CELL_PARAMS


# ---------------------------------------------------------------------------
# CC-BE-2414: Scoring tests
# ---------------------------------------------------------------------------

class TestBatteryScoring:
    def test_score_weights_sum_to_one(self):
        total = sum(BATTERY_SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_default_candidate_scores(self):
        baseline = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS)
        robustness = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline.metrics)
        eval_result = score_battery_candidate(
            baseline.metrics, baseline.metrics, robustness_profile=robustness,
        )
        assert 0 < eval_result.final_score <= 1.0
        assert eval_result.hard_fail is False

    def test_bad_coulombic_triggers_hard_fail(self):
        metrics = {"coulombic_efficiency": 85.0, "internal_resistance": 30}
        eval_result = score_battery_candidate(metrics, {"coulombic_efficiency": 99.5, "internal_resistance": 45})
        assert eval_result.hard_fail is True

    def test_high_resistance_triggers_hard_fail(self):
        metrics = {"coulombic_efficiency": 99.0, "internal_resistance": 250}
        eval_result = score_battery_candidate(metrics, {"coulombic_efficiency": 99.5, "internal_resistance": 45})
        assert eval_result.hard_fail is True

    def test_improved_candidate_scores_higher(self):
        baseline_metrics = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS).metrics
        # Better params: lower resistance, lower fade
        better_params = dict(DEFAULT_CELL_PARAMS, R0_mohm=20.0, R1_mohm=10.0, fade_rate_per_cycle=0.0002)
        better_metrics = run_experiment("baseline_cycle", better_params).metrics
        robustness_base = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline_metrics)
        robustness_better = compute_robustness_profile(better_params, baseline_metrics)
        score_base = score_battery_candidate(baseline_metrics, baseline_metrics, robustness_base)
        score_better = score_battery_candidate(better_metrics, baseline_metrics, robustness_better)
        assert score_better.final_score >= score_base.final_score


class TestRobustnessProfile:
    def test_profile_keys(self):
        baseline = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS)
        profile = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline.metrics)
        assert "worst_case_capacity_delta" in profile
        assert "crate_sensitivity" in profile
        assert "thermal_sensitivity" in profile
        assert "capacity_retention" in profile
        assert "fade_rate" in profile

    def test_default_params_reasonable(self):
        baseline = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS)
        profile = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline.metrics)
        assert profile["capacity_retention"] > 50.0
        assert profile["fade_rate"] >= 0


class TestCaveatGeneration:
    def test_caveats_include_param_changes(self):
        from breakthrough_engine.domain_models import CandidateSpec, EvaluationResult
        candidate = CandidateSpec(
            domain_name="battery_ecm",
            title="test",
            parameters=dict(DEFAULT_CELL_PARAMS, R0_mohm=15.0),
        )
        evaluation = EvaluationResult(
            candidate_id="test",
            domain_name="battery_ecm",
            score_components={"resistance_improvement": 0.9, "fade_improvement": 0.2},
            final_score=0.6,
        )
        baseline = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS).metrics
        cand_metrics = run_experiment("baseline_cycle", candidate.parameters).metrics
        caveats = generate_candidate_caveats(candidate, evaluation, baseline, cand_metrics)
        assert any("R0_mohm" in c for c in caveats)

    def test_caveats_include_score_concentration(self):
        from breakthrough_engine.domain_models import CandidateSpec, EvaluationResult
        candidate = CandidateSpec(
            domain_name="battery_ecm", title="test",
            parameters=dict(DEFAULT_CELL_PARAMS),
        )
        evaluation = EvaluationResult(
            candidate_id="test", domain_name="battery_ecm",
            score_components={"resistance_improvement": 0.95, "fade_improvement": 0.1},
            final_score=0.6,
        )
        baseline = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS).metrics
        caveats = generate_candidate_caveats(candidate, evaluation, baseline, baseline)
        assert any("concentrated" in c.lower() or "weakness" in c.lower() for c in caveats)


# ---------------------------------------------------------------------------
# CC-BE-2414: Full loop tests
# ---------------------------------------------------------------------------

class TestBatteryLoop:
    @pytest.fixture
    def db_repo(self):
        db = init_db(in_memory=True)
        return Repository(db)

    def test_loop_runs_successfully(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=42)
        result = loop.run(run_id="test_1")
        assert result.total_candidates == 3
        # promoted + rejected + hard_fail + alternate(deferred) == total
        alternate_count = 1 if result.alternate else 0
        assert result.promoted_count + result.rejected_count + result.hard_fail_count + alternate_count == 3

    def test_loop_persists_candidates(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="persist_test")
        candidates = db_repo.list_domain_candidates("battery_ecm")
        assert len(candidates) == 3

    def test_loop_persists_promotions(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="promo_test")
        promos = db_repo.list_promotion_records("battery_ecm")
        assert len(promos) == 3

    def test_loop_persists_memory(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="mem_test")
        ideas = db_repo.list_idea_memory("battery_ecm")
        exp_mem = db_repo.list_experiment_memory("battery_ecm")
        assert len(ideas) == 3
        assert len(exp_mem) == 3

    def test_selective_promotion_at_most_one(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=6, seed=42)
        result = loop.run(run_id="selective_test")
        assert result.promoted_count <= 1

    def test_summary_is_json_serializable(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=42)
        result = loop.run(run_id="json_test")
        summary = result.summary()
        json_str = json.dumps(summary, default=str)
        loaded = json.loads(json_str)
        assert loaded["total_candidates"] == 3

    def test_does_not_touch_pv_tables(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="isolation_test")
        pv_candidates = db_repo.list_domain_candidates("pv_iv")
        assert len(pv_candidates) == 0

    def test_high_threshold_rejects_all(self, db_repo):
        loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=42, promotion_threshold=0.99)
        result = loop.run(run_id="high_thresh")
        assert result.promoted_count == 0

    def test_three_sequential_runs_accumulate_memory(self, db_repo):
        for i in range(3):
            loop = BatteryOptimizationLoop(db_repo, n_candidates=3, seed=i * 10 + 1)
            result = loop.run(run_id=f"multi_{i}")
            assert result.total_candidates == 3
        ideas = db_repo.list_idea_memory("battery_ecm", limit=100)
        assert len(ideas) == 9


# ---------------------------------------------------------------------------
# CC-BE-2414/2415: Benchmark tests
# ---------------------------------------------------------------------------

class TestBatteryBenchmark:
    @pytest.fixture
    def db_repo(self):
        db = init_db(in_memory=True)
        return Repository(db)

    def test_benchmark_report_structure(self, db_repo):
        report = run_battery_benchmark(db_repo, n_candidates=3, seed=42)
        assert report["benchmark_domain"] == "battery_ecm"
        assert "baseline_candidate" in report
        assert "reference_comparison" in report
        assert "summary" in report

    def test_benchmark_baseline_metrics(self, db_repo):
        report = run_battery_benchmark(db_repo, n_candidates=3, seed=42)
        baseline = report["baseline_candidate"]["baseline_metrics"]
        assert baseline["discharge_capacity"] > 0
        assert baseline["coulombic_efficiency"] > 90

    def test_benchmark_reference_comparison(self, db_repo):
        report = run_battery_benchmark(db_repo, n_candidates=3, seed=42)
        ref = report["reference_comparison"]
        assert ref["reference_name"] == "benchmark_nmc_21700_3200mah"
        assert "reference_metrics" in ref

    def test_benchmark_deterministic(self, db_repo):
        r1 = run_battery_benchmark(db_repo, n_candidates=3, seed=42)
        db2 = init_db(in_memory=True)
        repo2 = Repository(db2)
        r2 = run_battery_benchmark(repo2, n_candidates=3, seed=42)
        assert r1["promotion_decision"] == r2["promotion_decision"]

    def test_benchmark_json_serializable(self, db_repo):
        report = run_battery_benchmark(db_repo, n_candidates=3, seed=42)
        json_str = json.dumps(report, default=str)
        loaded = json.loads(json_str)
        assert loaded["benchmark_domain"] == "battery_ecm"
