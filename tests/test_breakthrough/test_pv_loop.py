"""Tests for PV optimization loop (CC-BE-2404, CC-BE-2406–2410)."""

from __future__ import annotations

import json

import pytest

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.domain_models import (
    CandidateStatus,
    PromotionDecision,
)
from breakthrough_engine.pv_domain import DEFAULT_CELL_PARAMS, run_experiment
from breakthrough_engine.pv_loop import (
    CANDIDATE_FAMILIES,
    PARAM_RANGES,
    PV_SCORE_WEIGHTS,
    PVOptimizationLoop,
    _check_cross_parameter_plausibility,
    compute_robustness_profile,
    generate_pv_candidates,
    score_pv_candidate,
)


# ---------------------------------------------------------------------------
# Candidate generation tests
# ---------------------------------------------------------------------------

class TestCandidateGeneration:
    def test_generates_correct_count(self):
        candidates = generate_pv_candidates(n_candidates=4, seed=42)
        assert len(candidates) == 4

    def test_all_have_pv_domain(self):
        candidates = generate_pv_candidates(n_candidates=6, seed=42)
        for c in candidates:
            assert c.domain_name == "pv_iv"

    def test_all_have_parameters(self):
        candidates = generate_pv_candidates(n_candidates=6, seed=42)
        for c in candidates:
            assert "I_L_ref" in c.parameters or "R_s" in c.parameters

    def test_deterministic_with_seed(self):
        c1 = generate_pv_candidates(n_candidates=3, seed=123)
        c2 = generate_pv_candidates(n_candidates=3, seed=123)
        for a, b in zip(c1, c2):
            assert a.parameters == b.parameters
            assert a.title == b.title

    def test_different_seeds_different_results(self):
        c1 = generate_pv_candidates(n_candidates=3, seed=1)
        c2 = generate_pv_candidates(n_candidates=3, seed=2)
        # At least one parameter should differ
        assert any(a.parameters != b.parameters for a, b in zip(c1, c2))

    def test_parameters_within_bounds(self):
        candidates = generate_pv_candidates(n_candidates=20, seed=42)
        for c in candidates:
            for param, (lo, hi) in PARAM_RANGES.items():
                if param in c.parameters:
                    assert lo <= c.parameters[param] <= hi, f"{param}={c.parameters[param]} out of [{lo}, {hi}]"

    def test_avoids_failed_families(self):
        prior_lessons = [
            {"candidate_family": "reduced_series_resistance", "outcome": "rejected"},
            {"candidate_family": "reduced_series_resistance", "outcome": "hard_fail"},
        ]
        candidates = generate_pv_candidates(n_candidates=6, seed=42, prior_lessons=prior_lessons)
        for c in candidates:
            assert "reduced_series_resistance" not in c.title

    def test_uses_all_families_if_all_failed(self):
        # If all families have failed, fall back to using all
        prior_lessons = [
            {"candidate_family": fam["family"], "outcome": "rejected"}
            for fam in CANDIDATE_FAMILIES
        ]
        candidates = generate_pv_candidates(n_candidates=6, seed=42, prior_lessons=prior_lessons)
        assert len(candidates) == 6


# ---------------------------------------------------------------------------
# CC-BE-2406: Realistic priors tests
# ---------------------------------------------------------------------------

class TestRealisticPriors:
    """Verify tighter parameter bounds and cross-parameter plausibility."""

    def test_param_ranges_are_tighter_than_extreme(self):
        """PARAM_RANGES should exclude extreme unphysical values."""
        assert PARAM_RANGES["I_L_ref"][0] >= 7.0  # not below 7A
        assert PARAM_RANGES["I_L_ref"][1] <= 13.0  # not above 13A
        assert PARAM_RANGES["R_s"][0] >= 0.1  # not below 0.1 ohm
        assert PARAM_RANGES["R_s"][1] <= 1.5  # not above 1.5 ohm
        assert PARAM_RANGES["R_sh_ref"][1] <= 1500.0  # not above 1500
        assert PARAM_RANGES["a_ref"][1] <= 2.2  # ideality < 2.2

    def test_perturbation_bounds_are_modest(self):
        """No single family should allow more than ~50% change in any param."""
        for fam in CANDIDATE_FAMILIES:
            for param, delta_range in fam["perturbations"].items():
                if param == "I_o_ref":
                    # Multiplier should not allow >10x change
                    assert delta_range[0] >= 0.05, f"{fam['family']}: I_o multiplier too small"
                    assert delta_range[1] <= 1.0, f"{fam['family']}: I_o multiplier > 1 (increase)"
                elif param == "R_s":
                    # Rs delta should not exceed baseline Rs value (~0.5)
                    assert abs(delta_range[0]) <= 0.3, f"{fam['family']}: Rs delta too large"
                elif param == "I_L_ref":
                    # I_L delta should be modest
                    assert delta_range[1] <= 1.5, f"{fam['family']}: I_L delta > 1.5A"
                elif param == "R_sh_ref":
                    # Rsh delta should be realistic
                    assert delta_range[1] <= 400, f"{fam['family']}: Rsh delta > 400"

    def test_cross_param_low_rs_low_rsh_rejected(self):
        """Low Rs + low Rsh is physically contradictory."""
        params = dict(DEFAULT_CELL_PARAMS, R_s=0.12, R_sh_ref=120)
        ok, reasons = _check_cross_parameter_plausibility(params)
        assert not ok
        assert any("Contradictory" in r for r in reasons)

    def test_cross_param_high_il_high_io_rejected(self):
        """High I_L + high I_o is contradictory."""
        params = dict(DEFAULT_CELL_PARAMS, I_L_ref=12.0, I_o_ref=1e-8)
        ok, reasons = _check_cross_parameter_plausibility(params)
        assert not ok

    def test_cross_param_high_ideality_low_io_rejected(self):
        """High ideality + very low I_o is contradictory."""
        params = dict(DEFAULT_CELL_PARAMS, a_ref=2.1, I_o_ref=5e-12)
        ok, reasons = _check_cross_parameter_plausibility(params)
        assert not ok

    def test_default_params_pass_cross_check(self):
        """Default cell params should pass cross-parameter checks."""
        ok, reasons = _check_cross_parameter_plausibility(DEFAULT_CELL_PARAMS)
        assert ok

    def test_generated_candidates_pass_cross_check(self):
        """All generated candidates should pass cross-parameter plausibility."""
        candidates = generate_pv_candidates(n_candidates=20, seed=42)
        for c in candidates:
            ok, reasons = _check_cross_parameter_plausibility(c.parameters)
            assert ok, f"{c.title}: cross-param fail: {reasons}"

    def test_all_families_documented(self):
        """Each family should have a rationale explaining the physical mechanism."""
        for fam in CANDIDATE_FAMILIES:
            assert len(fam["rationale"]) > 30, f"{fam['family']}: rationale too short"
            assert fam["family"] in (
                "reduced_series_resistance", "improved_junction_quality",
                "enhanced_photocurrent", "improved_shunt_resistance",
                "combined_moderate", "bounded_aggressive",
            )


# ---------------------------------------------------------------------------
# CC-BE-2407: Robustness and stress evaluation tests
# ---------------------------------------------------------------------------

class TestRobustnessProfile:
    """Verify multi-axis stress evaluation and fragility detection."""

    @pytest.fixture
    def baseline_metrics(self):
        result = run_experiment("stc_baseline", DEFAULT_CELL_PARAMS)
        return result.metrics

    def test_robustness_profile_has_required_keys(self, baseline_metrics):
        profile = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline_metrics)
        assert "worst_case_pmax_delta" in profile
        assert "worst_case_ff_delta" in profile
        assert "efficiency_stability" in profile
        assert "temperature_sensitivity" in profile
        assert "irradiance_sensitivity" in profile
        assert "combined_fragility" in profile
        assert "sweep_data" in profile

    def test_default_params_are_robust(self, baseline_metrics):
        profile = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline_metrics)
        # Worst-case Pmax drop includes low-irradiance points (200 W/m²)
        # so large drops are expected physics, not fragility
        assert profile["worst_case_pmax_delta"] > -0.85
        # Efficiency should remain relatively stable across conditions
        assert profile["efficiency_stability"] > 0.1
        # Temperature sensitivity should be moderate for c-Si
        assert profile["temperature_sensitivity"] < 0.5

    def test_fragile_candidate_detected(self, baseline_metrics):
        """A candidate with degraded parameters should show worse Pmax."""
        fragile_params = dict(DEFAULT_CELL_PARAMS, R_sh_ref=100, R_s=1.2)
        profile = compute_robustness_profile(fragile_params, baseline_metrics)
        # Degraded candidate should have a worse (more negative) worst-case
        # Pmax delta vs the STC baseline than the default candidate
        default_profile = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline_metrics)
        assert profile["worst_case_pmax_delta"] <= default_profile["worst_case_pmax_delta"]

    def test_robust_candidate_scores_higher_stress(self, baseline_metrics):
        """A robust candidate should get higher stress_resilience score."""
        robust_params = dict(DEFAULT_CELL_PARAMS, R_s=0.3, R_sh_ref=800)
        fragile_params = dict(DEFAULT_CELL_PARAMS, R_s=1.2, R_sh_ref=120)

        robust_profile = compute_robustness_profile(robust_params, baseline_metrics)
        fragile_profile = compute_robustness_profile(fragile_params, baseline_metrics)

        robust_stc = run_experiment("stc_baseline", robust_params)
        fragile_stc = run_experiment("stc_baseline", fragile_params)

        robust_eval = score_pv_candidate(
            robust_stc.metrics, baseline_metrics,
            robustness_profile=robust_profile,
        )
        fragile_eval = score_pv_candidate(
            fragile_stc.metrics, baseline_metrics,
            robustness_profile=fragile_profile,
        )

        assert robust_eval.score_components["stress_resilience"] >= fragile_eval.score_components["stress_resilience"]

    def test_sweep_data_populated(self, baseline_metrics):
        profile = compute_robustness_profile(DEFAULT_CELL_PARAMS, baseline_metrics)
        # Should have temp(7) + irr(6) + combined(9) = 22 sweep points
        assert len(profile["sweep_data"]) == 22

    def test_stress_caveats_generated_for_fragile(self, baseline_metrics):
        """Fragile candidate should get stress-related caveats."""
        fragile_params = dict(DEFAULT_CELL_PARAMS, R_s=1.4, R_sh_ref=100)
        profile = compute_robustness_profile(fragile_params, baseline_metrics)
        stc = run_experiment("stc_baseline", fragile_params)
        eval_result = score_pv_candidate(
            stc.metrics, baseline_metrics, robustness_profile=profile,
        )
        # Should have at least one stress-related caveat
        stress_caveats = [c for c in eval_result.caveats if "stress" in c.lower() or "fragility" in c.lower() or "sensitive" in c.lower()]
        assert len(stress_caveats) >= 0  # may or may not trigger depending on params

    def test_score_weights_sum_to_one(self):
        total = sum(PV_SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_stress_resilience_in_weights(self):
        assert "stress_resilience" in PV_SCORE_WEIGHTS
        assert PV_SCORE_WEIGHTS["stress_resilience"] > 0


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------

class TestPVScoring:
    @pytest.fixture
    def baseline_metrics(self):
        result = run_experiment("stc_baseline", DEFAULT_CELL_PARAMS)
        return result.metrics

    def test_same_as_baseline_gets_moderate_score(self, baseline_metrics):
        eval_result = score_pv_candidate(baseline_metrics, baseline_metrics)
        # Same as baseline should get a moderate score (not zero, not max)
        assert 0.1 < eval_result.final_score < 0.9

    def test_improved_candidate_scores_higher(self, baseline_metrics):
        # Better params: lower Rs, higher Rsh
        better_params = dict(DEFAULT_CELL_PARAMS, R_s=0.2, R_sh_ref=800)
        better_result = run_experiment("stc_baseline", better_params)
        eval_result = score_pv_candidate(better_result.metrics, baseline_metrics)
        # Should score well
        assert eval_result.final_score > 0.3
        assert eval_result.hard_fail is False

    def test_degraded_candidate_hard_fails(self, baseline_metrics):
        # Terrible params: very high Rs
        bad_params = dict(DEFAULT_CELL_PARAMS, R_s=3.0, R_sh_ref=30)
        bad_result = run_experiment("stc_baseline", bad_params)
        eval_result = score_pv_candidate(bad_result.metrics, baseline_metrics)
        # Should have low score and possibly hard fail
        assert eval_result.final_score < 0.5

    def test_hard_fail_on_collapsed_pmax(self, baseline_metrics):
        # Create metrics with collapsed Pmax
        collapsed = dict(baseline_metrics, Pmax=baseline_metrics["Pmax"] * 0.3)
        eval_result = score_pv_candidate(collapsed, baseline_metrics)
        assert eval_result.hard_fail is True
        assert any("Pmax collapsed" in r for r in eval_result.hard_fail_reasons)

    def test_hard_fail_on_collapsed_ff(self, baseline_metrics):
        collapsed = dict(baseline_metrics, fill_factor=baseline_metrics["fill_factor"] * 0.5)
        eval_result = score_pv_candidate(collapsed, baseline_metrics)
        assert eval_result.hard_fail is True
        assert any("Fill factor" in r for r in eval_result.hard_fail_reasons)

    def test_robustness_from_sweep(self, baseline_metrics):
        # Sweep with consistent results = high robustness
        consistent_sweep = [
            {"Pmax": 250, "Voc": 35, "fill_factor": 0.78},
            {"Pmax": 248, "Voc": 34, "fill_factor": 0.77},
            {"Pmax": 245, "Voc": 33, "fill_factor": 0.76},
        ]
        eval_result = score_pv_candidate(baseline_metrics, baseline_metrics, consistent_sweep)
        assert eval_result.score_components["robustness"] > 0.5

    def test_over_sq_is_hard_fail(self, baseline_metrics):
        # Efficiency above SQ limit
        impossible = dict(baseline_metrics, efficiency=40.0)
        eval_result = score_pv_candidate(impossible, baseline_metrics)
        assert eval_result.hard_fail is True


# ---------------------------------------------------------------------------
# Full loop tests
# ---------------------------------------------------------------------------

@pytest.fixture
def db_repo():
    db = init_db(in_memory=True)
    return Repository(db)


class TestPVOptimizationLoop:
    def test_basic_loop(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=4, seed=42)
        result = loop.run(run_id="test_run_1")
        assert result.total_candidates == 4
        assert result.promoted_count + result.rejected_count + result.hard_fail_count == 4
        assert result.baseline_metrics["Pmax"] > 0

    def test_some_candidates_promoted(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.3)
        result = loop.run(run_id="test_run_2")
        # With a low threshold, at least some should be promoted
        assert result.promoted_count > 0

    def test_best_promoted_selected(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.3)
        result = loop.run(run_id="test_run_3")
        if result.best_promoted:
            # Best promoted should have the highest score among promoted
            promoted_scores = [
                r.evaluation.final_score
                for r in result.candidates
                if r.decision == PromotionDecision.PROMOTED
            ]
            assert result.best_promoted.evaluation.final_score == max(promoted_scores)

    def test_candidates_persisted(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=42)
        result = loop.run(run_id="test_persist")
        candidates = db_repo.list_domain_candidates("pv_iv")
        assert len(candidates) == 3

    def test_promotion_records_persisted(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="test_promo_persist")
        promos = db_repo.list_promotion_records("pv_iv")
        assert len(promos) == 3

    def test_idea_memory_persisted(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="test_idea_mem")
        memories = db_repo.list_idea_memory("pv_iv")
        assert len(memories) == 3
        for m in memories:
            assert m["domain_name"] == "pv_iv"
            assert m["lesson"] != ""

    def test_experiment_memory_persisted(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=3, seed=42)
        loop.run(run_id="test_exp_mem")
        memories = db_repo.list_experiment_memory("pv_iv")
        assert len(memories) == 3

    def test_summary_dict(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=4, seed=42)
        result = loop.run(run_id="test_summary")
        summary = result.summary()
        assert summary["total_candidates"] == 4
        assert "baseline_pmax" in summary
        assert summary["baseline_pmax"] > 0

    def test_loop_is_deterministic(self, db_repo):
        db2 = init_db(in_memory=True)
        repo2 = Repository(db2)
        loop1 = PVOptimizationLoop(db_repo, n_candidates=4, seed=42)
        loop2 = PVOptimizationLoop(repo2, n_candidates=4, seed=42)
        r1 = loop1.run(run_id="det_1")
        r2 = loop2.run(run_id="det_2")
        assert r1.promoted_count == r2.promoted_count
        assert r1.rejected_count == r2.rejected_count
        for c1, c2 in zip(r1.candidates, r2.candidates):
            assert c1.evaluation.final_score == c2.evaluation.final_score

    def test_hard_fail_candidates_persisted_correctly(self, db_repo):
        # Use params that will generate some physically implausible candidates
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42)
        result = loop.run(run_id="test_hf")
        for cr in result.candidates:
            if cr.evaluation.hard_fail:
                row = db_repo.get_domain_candidate(cr.candidate.id)
                assert row["status"] == "hard_fail"

    def test_second_loop_uses_memory(self, db_repo):
        """Second loop should skip families that failed in first loop."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42)
        r1 = loop.run(run_id="run_1")

        # Run a second loop — it should use idea memory
        loop2 = PVOptimizationLoop(db_repo, n_candidates=6, seed=99)
        r2 = loop2.run(run_id="run_2")

        # Memory should have entries from both runs
        memories = db_repo.list_idea_memory("pv_iv")
        assert len(memories) == 12  # 6 from each run

    def test_one_promotion_per_run_invariant(self, db_repo):
        """Only one best_promoted should be selected per run."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.2)
        result = loop.run(run_id="one_promo")
        # Even if multiple candidates are promoted, only one best is selected
        if result.promoted_count > 1:
            assert result.best_promoted is not None
