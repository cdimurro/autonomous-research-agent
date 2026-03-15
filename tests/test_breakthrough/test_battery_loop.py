"""Tests for Battery optimization loop (CC-BE-2413 through CC-BE-2415)."""

from __future__ import annotations

import json

import pytest

from breakthrough_engine.battery_domain import DEFAULT_CELL_PARAMS
from breakthrough_engine.battery_loop import (
    CANDIDATE_FAMILIES,
    PARAM_RANGES,
    PROPOSAL_TAG_EXPLORATORY,
    PROPOSAL_TAG_MEMORY,
    PROPOSAL_TAG_RECOVERY,
    PROPOSAL_TAG_RETRY,
    _check_cross_parameter_plausibility,
    _compute_family_weights,
    generate_battery_candidates,
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
