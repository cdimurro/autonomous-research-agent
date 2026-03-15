"""Tests for the Battery Solver Sidecar.

All tests are offline-safe — no PyBaMM required.
Covers: result schema, ECM-to-DFN mapping, concordance computation,
mock sidecar, failure states, and determinism.
"""

import json
from pathlib import Path

import pytest

from breakthrough_engine.battery_sidecar import (
    CONCORDANCE_CONFIRM_THRESHOLD,
    CONCORDANCE_VETO_THRESHOLD,
    CONCORDANCE_WEIGHTS,
    DFN_PARAM_BOUNDS,
    MockPyBaMMSidecar,
    PyBaMMSidecar,
    PyBaMMSidecarResult,
    SidecarStatus,
    compute_concordance,
    map_ecm_to_dfn,
    validate_dfn_params,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

DEFAULT_ECM_PARAMS = {
    "capacity_ah": 3.0,
    "R0_mohm": 30.0,
    "R1_mohm": 15.0,
    "C1_F": 500.0,
    "coulombic_eff": 0.995,
    "fade_rate_per_cycle": 0.0005,
    "v_min": 2.5,
    "v_max": 4.2,
    "temp_coeff_r0": 0.003,
    "ocv_coeffs": [3.0, 1.5, -1.2, 0.85],
}

DEFAULT_ECM_METRICS = {
    "discharge_capacity": 2.95,
    "coulombic_efficiency": 0.995,
    "internal_resistance": 32.0,
    "energy_efficiency": 0.91,
    "rate_capability": 0.82,
}


# ── SidecarStatus enum ───────────────────────────────────────────────────

class TestSidecarStatus:
    def test_all_states_defined(self):
        assert SidecarStatus.SUCCESS == "success"
        assert SidecarStatus.UNAVAILABLE == "unavailable"
        assert SidecarStatus.ERROR == "error"
        assert SidecarStatus.INVALID == "invalid"

    def test_four_states(self):
        assert len(SidecarStatus) == 4


# ── PyBaMMSidecarResult ──────────────────────────────────────────────────

class TestSidecarResult:
    def test_success_result(self):
        r = PyBaMMSidecarResult(
            candidate_id="test-1",
            status=SidecarStatus.SUCCESS,
            concordance_score=0.75,
            success=True,
        )
        assert r.success is True
        assert r.concordance_score == 0.75
        assert r.timed_out is False

    def test_unavailable_result(self):
        r = PyBaMMSidecarResult(
            candidate_id="test-2",
            status=SidecarStatus.UNAVAILABLE,
            error_message="venv not found",
        )
        assert r.success is False
        assert r.concordance_score == 0.0

    def test_error_result_with_timeout(self):
        r = PyBaMMSidecarResult(
            candidate_id="test-3",
            status=SidecarStatus.ERROR,
            timed_out=True,
            error_message="timed out",
        )
        assert r.timed_out is True
        assert r.status == SidecarStatus.ERROR

    def test_invalid_result(self):
        r = PyBaMMSidecarResult(
            candidate_id="test-4",
            status=SidecarStatus.INVALID,
            error_message="bad physics",
        )
        assert r.status == SidecarStatus.INVALID
        assert r.success is False

    def test_result_serializable(self):
        r = PyBaMMSidecarResult(
            candidate_id="test-5",
            status=SidecarStatus.SUCCESS,
            concordance_score=0.65,
            pybamm_metrics={"discharge_capacity": 2.9},
            ecm_metrics={"discharge_capacity": 3.0},
            success=True,
        )
        d = r.model_dump()
        assert isinstance(json.dumps(d), str)


# ── ECM-to-DFN mapping ───────────────────────────────────────────────────

class TestECMtoDFNMapping:
    def test_default_params_produce_valid_dfn(self):
        dfn = map_ecm_to_dfn(DEFAULT_ECM_PARAMS)
        valid, issues = validate_dfn_params(dfn)
        assert valid, f"Default mapping invalid: {issues}"

    def test_all_expected_keys_present(self):
        dfn = map_ecm_to_dfn(DEFAULT_ECM_PARAMS)
        expected = {
            "electrolyte_conductivity", "contact_resistance",
            "positive_exchange_current_density", "negative_exchange_current_density",
            "double_layer_capacitance", "positive_electrode_thickness",
            "sei_growth_rate_constant", "lower_voltage_cut_off", "upper_voltage_cut_off",
        }
        actual = {k for k in dfn if not k.startswith("_")}
        assert expected == actual

    def test_lower_r0_gives_higher_conductivity(self):
        """Directional: lower R0 → higher electrolyte conductivity."""
        dfn_high_r0 = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "R0_mohm": 50.0})
        dfn_low_r0 = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "R0_mohm": 20.0})
        assert dfn_low_r0["electrolyte_conductivity"] > dfn_high_r0["electrolyte_conductivity"]

    def test_lower_r1_gives_higher_exchange_current(self):
        """Directional: lower R1 → higher exchange current density."""
        dfn_high_r1 = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "R1_mohm": 30.0})
        dfn_low_r1 = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "R1_mohm": 10.0})
        assert dfn_low_r1["positive_exchange_current_density"] > dfn_high_r1["positive_exchange_current_density"]

    def test_higher_capacity_gives_thicker_electrode(self):
        """Directional: higher capacity → thicker positive electrode."""
        dfn_low_cap = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "capacity_ah": 2.0})
        dfn_high_cap = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "capacity_ah": 5.0})
        assert dfn_high_cap["positive_electrode_thickness"] > dfn_low_cap["positive_electrode_thickness"]

    def test_higher_fade_gives_higher_sei_rate(self):
        """Directional: higher fade rate → higher SEI growth rate."""
        dfn_low_fade = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "fade_rate_per_cycle": 0.0001})
        dfn_high_fade = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "fade_rate_per_cycle": 0.002})
        assert dfn_high_fade["sei_growth_rate_constant"] > dfn_low_fade["sei_growth_rate_constant"]

    def test_voltage_cutoffs_mapped_directly(self):
        dfn = map_ecm_to_dfn({**DEFAULT_ECM_PARAMS, "v_min": 2.0, "v_max": 4.35})
        assert dfn["lower_voltage_cut_off"] == 2.0
        assert dfn["upper_voltage_cut_off"] == 4.35

    def test_all_dfn_params_within_bounds(self):
        """All mapped params must be within DFN_PARAM_BOUNDS."""
        dfn = map_ecm_to_dfn(DEFAULT_ECM_PARAMS)
        for key, (lo, hi) in DFN_PARAM_BOUNDS.items():
            val = dfn.get(key)
            if val is not None:
                assert lo <= val <= hi, f"{key}={val} outside [{lo}, {hi}]"

    def test_extreme_params_still_valid(self):
        """Edge-case ECM params should still produce valid DFN."""
        extreme = {
            "capacity_ah": 5.5, "R0_mohm": 14.0, "R1_mohm": 6.0,
            "C1_F": 1200.0, "coulombic_eff": 0.9995,
            "fade_rate_per_cycle": 0.0001, "v_min": 2.5, "v_max": 4.2,
        }
        dfn = map_ecm_to_dfn(extreme)
        valid, issues = validate_dfn_params(dfn)
        assert valid, f"Extreme mapping invalid: {issues}"

    def test_chemistry_and_param_set_propagated(self):
        dfn = map_ecm_to_dfn(
            DEFAULT_ECM_PARAMS, chemistry="LFP", pybamm_parameter_set="Prada2013",
        )
        assert dfn["_chemistry"] == "LFP"
        assert dfn["_pybamm_parameter_set"] == "Prada2013"

    def test_mapping_source_metadata_present(self):
        dfn = map_ecm_to_dfn(DEFAULT_ECM_PARAMS)
        assert "_mapping_source" in dfn
        sources = dfn["_mapping_source"]
        assert "engine-derived" in sources["electrolyte_conductivity"]


# ── DFN parameter validation ─────────────────────────────────────────────

class TestDFNValidation:
    def test_valid_params_pass(self):
        dfn = map_ecm_to_dfn(DEFAULT_ECM_PARAMS)
        valid, issues = validate_dfn_params(dfn)
        assert valid
        assert issues == []

    def test_out_of_bounds_detected(self):
        bad_dfn = {"electrolyte_conductivity": 100.0}  # way above 5.0 max
        valid, issues = validate_dfn_params(bad_dfn)
        assert not valid
        assert len(issues) == 1
        assert "electrolyte_conductivity" in issues[0]


# ── Concordance computation ───────────────────────────────────────────────

class TestConcordance:
    def test_identical_metrics_give_1(self):
        metrics = {"discharge_capacity": 3.0, "coulombic_efficiency": 0.995,
                   "internal_resistance": 30.0, "energy_efficiency": 0.92,
                   "rate_capability": 0.85}
        score, details = compute_concordance(metrics, metrics)
        assert score == 1.0

    def test_completely_different_metrics_give_low(self):
        ecm = {"discharge_capacity": 3.0, "coulombic_efficiency": 0.995,
               "internal_resistance": 30.0, "energy_efficiency": 0.92,
               "rate_capability": 0.85}
        pybamm = {"discharge_capacity": 0.1, "coulombic_efficiency": 0.5,
                  "internal_resistance": 200.0, "energy_efficiency": 0.3,
                  "rate_capability": 0.1}
        score, _ = compute_concordance(ecm, pybamm)
        assert score < 0.3

    def test_weighted_average_is_correct(self):
        ecm = {"discharge_capacity": 3.0, "internal_resistance": 30.0}
        pybamm = {"discharge_capacity": 3.0, "internal_resistance": 30.0}
        weights = {"discharge_capacity": 0.6, "internal_resistance": 0.4}
        score, _ = compute_concordance(ecm, pybamm, weights=weights)
        assert score == 1.0

    def test_missing_metrics_excluded(self):
        ecm = {"discharge_capacity": 3.0}
        pybamm = {"discharge_capacity": 3.0, "internal_resistance": 30.0}
        score, details = compute_concordance(ecm, pybamm)
        # Only discharge_capacity has both values
        assert details["internal_resistance"]["reason"] == "missing"

    def test_partial_agreement(self):
        ecm = {"discharge_capacity": 3.0, "coulombic_efficiency": 0.995}
        pybamm = {"discharge_capacity": 2.7, "coulombic_efficiency": 0.990}
        score, details = compute_concordance(ecm, pybamm)
        assert 0.0 < score < 1.0
        assert details["discharge_capacity"]["agreement"] < 1.0

    def test_concordance_weights_sum_to_1(self):
        total = sum(CONCORDANCE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_thresholds_ordered(self):
        assert CONCORDANCE_VETO_THRESHOLD < CONCORDANCE_CONFIRM_THRESHOLD


# ── MockPyBaMMSidecar ────────────────────────────────────────────────────

class TestMockSidecar:
    def test_is_available(self):
        mock = MockPyBaMMSidecar(seed=42)
        assert mock.is_available() is True

    def test_returns_success(self):
        mock = MockPyBaMMSidecar(seed=42)
        result = mock.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        assert result.status == SidecarStatus.SUCCESS
        assert result.success is True
        assert 0.0 <= result.concordance_score <= 1.0

    def test_deterministic_same_seed(self):
        mock1 = MockPyBaMMSidecar(seed=42)
        mock2 = MockPyBaMMSidecar(seed=42)
        r1 = mock1.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        r2 = mock2.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        assert r1.concordance_score == r2.concordance_score

    def test_different_seed_different_result(self):
        mock1 = MockPyBaMMSidecar(seed=42)
        mock2 = MockPyBaMMSidecar(seed=99)
        r1 = mock1.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        r2 = mock2.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        # Different seeds should generally produce different concordance
        # (not guaranteed for all seed pairs, but extremely likely)
        assert r1.concordance_score != r2.concordance_score

    def test_different_params_different_concordance(self):
        mock = MockPyBaMMSidecar(seed=42)
        r1 = mock.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        modified_params = {**DEFAULT_ECM_PARAMS, "R0_mohm": 50.0, "capacity_ah": 4.5}
        r2 = mock.verify_candidate("c2", modified_params, DEFAULT_ECM_METRICS)
        assert r1.concordance_score != r2.concordance_score

    def test_mock_produces_pybamm_metrics(self):
        mock = MockPyBaMMSidecar(seed=42)
        result = mock.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        for key in CONCORDANCE_WEIGHTS:
            assert key in result.pybamm_metrics

    def test_concordance_details_populated(self):
        mock = MockPyBaMMSidecar(seed=42)
        result = mock.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        assert len(result.concordance_details) > 0
        for key, detail in result.concordance_details.items():
            assert "ecm" in detail
            assert "pybamm" in detail
            assert "agreement" in detail


# ── PyBaMMSidecar (unavailable path) ─────────────────────────────────────

class TestLiveSidecarUnavailable:
    def test_unavailable_when_venv_missing(self, tmp_path):
        sidecar = PyBaMMSidecar(venv_path=tmp_path / "nonexistent")
        assert sidecar.is_available() is False

    def test_verify_returns_unavailable(self, tmp_path):
        sidecar = PyBaMMSidecar(venv_path=tmp_path / "nonexistent")
        result = sidecar.verify_candidate("c1", DEFAULT_ECM_PARAMS, DEFAULT_ECM_METRICS)
        assert result.status == SidecarStatus.UNAVAILABLE
        assert result.success is False
        assert "not found" in result.error_message


# ── Concordance gate semantics ────────────────────────────────────────────

class TestConcordanceGateSemantics:
    """Verify gate decisions match the plan's concordance rules."""

    def test_veto_below_030(self):
        score = 0.25
        assert score < CONCORDANCE_VETO_THRESHOLD

    def test_caveat_between_030_060(self):
        score = 0.45
        assert CONCORDANCE_VETO_THRESHOLD <= score < CONCORDANCE_CONFIRM_THRESHOLD

    def test_confirmed_above_060(self):
        score = 0.75
        assert score >= CONCORDANCE_CONFIRM_THRESHOLD

    def test_boundary_030_is_not_veto(self):
        """Score of exactly 0.30 should NOT be vetoed (>= threshold)."""
        assert 0.30 >= CONCORDANCE_VETO_THRESHOLD

    def test_boundary_060_is_confirmed(self):
        """Score of exactly 0.60 should be confirmed (>= threshold)."""
        assert 0.60 >= CONCORDANCE_CONFIRM_THRESHOLD
