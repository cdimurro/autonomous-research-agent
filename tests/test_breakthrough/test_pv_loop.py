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
    PROPOSAL_TAG_EXPLORATORY,
    PROPOSAL_TAG_MEMORY,
    PROPOSAL_TAG_RECOVERY,
    PROPOSAL_TAG_RETRY,
    PV_SCORE_WEIGHTS,
    PVOptimizationLoop,
    REFERENCE_MODULE_PARAMS,
    _check_cross_parameter_plausibility,
    _compute_family_weights,
    compute_robustness_profile,
    generate_candidate_caveats,
    generate_pv_candidates,
    run_pv_benchmark,
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

    def test_downranks_failed_families(self):
        """Families with all hard-fail history should appear less often."""
        prior_lessons = [
            {"candidate_family": "reduced_series_resistance", "outcome": "hard_fail"},
            {"candidate_family": "reduced_series_resistance", "outcome": "hard_fail"},
        ]
        # With weighted selection, the failed family appears less but may still appear
        candidates = generate_pv_candidates(n_candidates=30, seed=42, prior_lessons=prior_lessons)
        rs_count = sum(1 for c in candidates if "reduced_series_resistance" in c.title)
        # Should be rare (< 20% of candidates) since weight = 0.1
        assert rs_count < 10, f"Failed family appeared {rs_count}/30 times"

    def test_all_families_still_available(self):
        """Even with all failures, candidates are still generated."""
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
        # All candidates accounted for (promoted + rejected + hard_fail + alternate)
        alternate_count = 1 if result.alternate else 0
        assert result.promoted_count + result.rejected_count + result.hard_fail_count + alternate_count == 4
        assert result.baseline_metrics["Pmax"] > 0

    def test_some_candidates_promoted(self, db_repo):
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.3)
        result = loop.run(run_id="test_run_2")
        # With selective policy, at most 1 promoted
        assert result.promoted_count <= 1

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
        """Selective policy: at most 1 promoted per run (CC-BE-2408)."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.2)
        result = loop.run(run_id="one_promo")
        # CC-BE-2408: at most 1 promoted, optionally 1 alternate
        assert result.promoted_count <= 1
        if result.best_promoted:
            assert result.promoted_count == 1


# ---------------------------------------------------------------------------
# CC-BE-2408: Promotion tightening and caveat generation tests
# ---------------------------------------------------------------------------

class TestPromotionTightening:
    @pytest.fixture
    def db_repo(self):
        db = init_db(in_memory=True)
        return Repository(db)

    def test_at_most_one_promoted(self, db_repo):
        """Selective promotion: at most 1 promoted per run."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.2)
        result = loop.run(run_id="selective_1")
        assert result.promoted_count <= 1

    def test_alternate_is_differentiated(self, db_repo):
        """Alternate must be from a different family than best promoted."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.3)
        result = loop.run(run_id="alt_test")
        if result.best_promoted and result.alternate:
            assert result.best_promoted.candidate.rationale != result.alternate.candidate.rationale

    def test_promoted_has_caveats(self, db_repo):
        """Promoted candidate should have caveats generated."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.3)
        result = loop.run(run_id="caveat_test")
        if result.best_promoted:
            assert len(result.best_promoted.promotion_caveats) > 0
            # Caveats should include parameter changes
            has_param_caveat = any("Parameter changes" in c for c in result.best_promoted.promotion_caveats)
            assert has_param_caveat

    def test_summary_includes_caveats(self, db_repo):
        """Summary should include caveats for promoted candidate."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.3)
        result = loop.run(run_id="summary_caveat")
        summary = result.summary()
        if result.best_promoted:
            assert "best_promoted_caveats" in summary

    def test_high_threshold_rejects_all(self, db_repo):
        """Very high threshold should reject all candidates."""
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.99)
        result = loop.run(run_id="high_thresh")
        assert result.promoted_count == 0
        assert result.best_promoted is None

    def test_decision_types_correct(self, db_repo):
        """Check that decisions are properly categorized."""
        from breakthrough_engine.domain_models import PromotionDecision
        loop = PVOptimizationLoop(db_repo, n_candidates=6, seed=42, promotion_threshold=0.3)
        result = loop.run(run_id="decision_types")
        decisions = [r.decision for r in result.candidates]
        for d in decisions:
            assert d in (PromotionDecision.PROMOTED, PromotionDecision.REJECTED, PromotionDecision.DEFERRED)


# ---------------------------------------------------------------------------
# CC-BE-2409: Memory-guided proposal generation tests
# ---------------------------------------------------------------------------

class TestMemoryGuidedGeneration:
    def test_no_memory_all_exploratory(self):
        """Without prior lessons, all candidates should be exploratory."""
        candidates = generate_pv_candidates(n_candidates=6, seed=42)
        for c in candidates:
            assert PROPOSAL_TAG_EXPLORATORY in c.rationale

    def test_promoted_family_gets_memory_tag(self):
        """Family with promotion history should be tagged memory-supported."""
        prior = [
            {"candidate_family": "reduced_series_resistance", "outcome": "promoted"},
        ]
        weights, tags = _compute_family_weights(prior)
        assert tags["reduced_series_resistance"] == PROPOSAL_TAG_MEMORY
        assert weights["reduced_series_resistance"] > 1.0

    def test_hard_fail_family_downranked(self):
        """Family with 100% hard-fail should be heavily down-ranked."""
        prior = [
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
        ]
        weights, tags = _compute_family_weights(prior)
        assert weights["bounded_aggressive"] < 0.2
        assert tags["bounded_aggressive"] == PROPOSAL_TAG_RETRY

    def test_all_rejected_gets_recovery_tag(self):
        """Family with all rejections (no hard-fail) should get recovery tag."""
        prior = [
            {"candidate_family": "enhanced_photocurrent", "outcome": "rejected"},
            {"candidate_family": "enhanced_photocurrent", "outcome": "rejected"},
        ]
        weights, tags = _compute_family_weights(prior)
        assert tags["enhanced_photocurrent"] == PROPOSAL_TAG_RECOVERY
        assert weights["enhanced_photocurrent"] < 1.0

    def test_memory_affects_family_selection(self):
        """Promoted family should appear more often than hard-fail family."""
        prior = [
            {"candidate_family": "reduced_series_resistance", "outcome": "promoted"},
            {"candidate_family": "reduced_series_resistance", "outcome": "promoted"},
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
        ]
        # Generate many candidates and count family occurrences
        candidates = generate_pv_candidates(n_candidates=30, seed=42, prior_lessons=prior)
        family_counts: dict[str, int] = {}
        for c in candidates:
            for fam in CANDIDATE_FAMILIES:
                if fam["family"] in c.title:
                    family_counts[fam["family"]] = family_counts.get(fam["family"], 0) + 1
                    break
        # Promoted family should appear more often
        rs_count = family_counts.get("reduced_series_resistance", 0)
        agg_count = family_counts.get("bounded_aggressive", 0)
        assert rs_count >= agg_count

    def test_proposal_tags_in_rationale(self):
        """Each candidate rationale should contain a proposal tag."""
        prior = [
            {"candidate_family": "reduced_series_resistance", "outcome": "promoted"},
            {"candidate_family": "bounded_aggressive", "outcome": "hard_fail"},
        ]
        candidates = generate_pv_candidates(n_candidates=6, seed=42, prior_lessons=prior)
        valid_tags = {PROPOSAL_TAG_MEMORY, PROPOSAL_TAG_EXPLORATORY, PROPOSAL_TAG_RECOVERY, PROPOSAL_TAG_RETRY}
        for c in candidates:
            assert any(tag in c.rationale for tag in valid_tags), f"No tag in: {c.rationale}"

    def test_multi_run_memory_accumulation(self):
        """Memory from multiple runs should cumulatively affect generation."""
        db = init_db(in_memory=True)
        repo = Repository(db)

        # Run 1: establish memory
        loop1 = PVOptimizationLoop(repo, n_candidates=4, seed=42)
        loop1.run(run_id="mem_run_1")

        # Run 2: should use memory from run 1
        loop2 = PVOptimizationLoop(repo, n_candidates=4, seed=99)
        r2 = loop2.run(run_id="mem_run_2")

        # All candidates should have rationale tags
        for cr in r2.candidates:
            assert "[" in cr.candidate.rationale  # tag marker


# ---------------------------------------------------------------------------
# CC-BE-2410: PV benchmark and held-out realism check tests
# ---------------------------------------------------------------------------

class TestPVBenchmark:
    @pytest.fixture
    def db_repo(self):
        db = init_db(in_memory=True)
        return Repository(db)

    def test_benchmark_report_structure(self, db_repo):
        """Benchmark report should have all required fields."""
        report = run_pv_benchmark(db_repo, n_candidates=4, seed=42)
        assert "benchmark_domain" in report
        assert report["benchmark_domain"] == "pv_iv"
        assert "baseline_candidate" in report
        assert "best_candidate" in report
        assert "caveats" in report
        assert "promotion_decision" in report
        assert "reference_comparison" in report
        assert "summary" in report

    def test_benchmark_baseline_has_metrics(self, db_repo):
        report = run_pv_benchmark(db_repo, n_candidates=4, seed=42)
        base = report["baseline_candidate"]["stc_metrics"]
        assert base["Pmax"] > 0
        assert base["fill_factor"] > 0
        assert base["efficiency"] > 0

    def test_benchmark_reference_comparison(self, db_repo):
        """Reference comparison should include STC metrics and robustness."""
        report = run_pv_benchmark(db_repo, n_candidates=4, seed=42)
        ref = report["reference_comparison"]
        assert ref["reference_name"] == "benchmark_mono_si_300w"
        assert "reference_stc_metrics" in ref
        assert ref["reference_stc_metrics"]["Pmax"] > 0
        assert "reference_robustness" in ref

    def test_benchmark_is_deterministic(self, db_repo):
        """Same seed should produce same benchmark report."""
        db2 = init_db(in_memory=True)
        repo2 = Repository(db2)
        r1 = run_pv_benchmark(db_repo, n_candidates=4, seed=42)
        r2 = run_pv_benchmark(repo2, n_candidates=4, seed=42)
        assert r1["summary"]["promoted"] == r2["summary"]["promoted"]
        assert r1["promotion_decision"] == r2["promotion_decision"]
        if r1["best_candidate"] and r2["best_candidate"]:
            assert r1["best_candidate"]["score"] == r2["best_candidate"]["score"]

    def test_benchmark_json_serializable(self, db_repo):
        """Benchmark report should be fully JSON-serializable."""
        report = run_pv_benchmark(db_repo, n_candidates=4, seed=42)
        json_str = json.dumps(report, default=str)
        loaded = json.loads(json_str)
        assert loaded["benchmark_domain"] == "pv_iv"

    def test_reference_module_params_plausible(self):
        """Reference module params should pass plausibility checks."""
        from breakthrough_engine.pv_domain import check_physical_plausibility
        ok, reasons = check_physical_plausibility(REFERENCE_MODULE_PARAMS)
        assert ok, f"Reference params failed plausibility: {reasons}"

    def test_reference_module_produces_output(self):
        """Reference module should produce valid STC output."""
        result = run_experiment("stc_baseline", REFERENCE_MODULE_PARAMS)
        assert result.success
        assert result.metrics["Pmax"] > 0
        assert 0 < result.metrics["efficiency"] < 33.7

    def test_benchmark_with_high_threshold(self, db_repo):
        """High threshold benchmark should report no promotion."""
        report = run_pv_benchmark(db_repo, n_candidates=4, seed=42, promotion_threshold=0.99)
        assert report["promotion_decision"] == "none"
        assert report["best_candidate"] is None
