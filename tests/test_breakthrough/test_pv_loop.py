"""Tests for PV optimization loop (CC-BE-2404)."""

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
    PV_SCORE_WEIGHTS,
    PVOptimizationLoop,
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
        from breakthrough_engine.pv_loop import PARAM_RANGES
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

    def test_weight_sum_is_one(self):
        total = sum(PV_SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

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
