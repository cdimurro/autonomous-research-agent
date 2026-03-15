"""Tests for PV I-V domain pack (CC-BE-2403)."""

from __future__ import annotations

import pytest

from breakthrough_engine.pv_domain import (
    DEFAULT_CELL_PARAMS,
    EXPERIMENT_TEMPLATES,
    PV_DOMAIN,
    PV_METRICS,
    _run_single_condition,
    check_metrics_plausibility,
    check_physical_plausibility,
    run_experiment,
)


# ---------------------------------------------------------------------------
# Domain spec tests
# ---------------------------------------------------------------------------

class TestPVDomain:
    def test_domain_name(self):
        assert PV_DOMAIN.name == "pv_iv"
        assert PV_DOMAIN.display_name == "PV I-V Characterization"

    def test_metrics_defined(self):
        assert len(PV_METRICS) == 7
        names = [m.name for m in PV_METRICS]
        assert "Voc" in names
        assert "Isc" in names
        assert "Pmax" in names
        assert "fill_factor" in names
        assert "efficiency" in names

    def test_primary_metrics(self):
        primary = [m for m in PV_METRICS if m.is_primary]
        assert len(primary) == 5  # Voc, Isc, Pmax, fill_factor, efficiency

    def test_banned_claims(self):
        assert len(PV_DOMAIN.banned_claims) >= 3
        assert any("perpetual" in c for c in PV_DOMAIN.banned_claims)

    def test_safety_constraints(self):
        assert any("Shockley-Queisser" in c for c in PV_DOMAIN.safety_constraints)


class TestExperimentTemplates:
    def test_all_templates_exist(self):
        assert "stc_baseline" in EXPERIMENT_TEMPLATES
        assert "irradiance_sweep" in EXPERIMENT_TEMPLATES
        assert "temperature_sweep" in EXPERIMENT_TEMPLATES
        assert "combined_sensitivity" in EXPERIMENT_TEMPLATES

    def test_stc_params(self):
        stc = EXPERIMENT_TEMPLATES["stc_baseline"]
        assert stc.parameters["irradiance"] == 1000
        assert stc.parameters["temperature"] == 25


# ---------------------------------------------------------------------------
# Single condition tests
# ---------------------------------------------------------------------------

class TestSingleCondition:
    def test_stc(self):
        metrics = _run_single_condition(DEFAULT_CELL_PARAMS, 1000, 25)
        assert metrics["Voc"] > 0
        assert metrics["Isc"] > 0
        assert metrics["Pmax"] > 0
        assert 0 < metrics["fill_factor"] < 1
        assert 0 < metrics["efficiency"] < 100

    def test_voc_decreases_with_temperature(self):
        m25 = _run_single_condition(DEFAULT_CELL_PARAMS, 1000, 25)
        m65 = _run_single_condition(DEFAULT_CELL_PARAMS, 1000, 65)
        # Voc should decrease with temperature for Si
        assert m65["Voc"] < m25["Voc"]

    def test_isc_increases_with_irradiance(self):
        m500 = _run_single_condition(DEFAULT_CELL_PARAMS, 500, 25)
        m1000 = _run_single_condition(DEFAULT_CELL_PARAMS, 1000, 25)
        assert m1000["Isc"] > m500["Isc"]

    def test_pmax_increases_with_irradiance(self):
        m400 = _run_single_condition(DEFAULT_CELL_PARAMS, 400, 25)
        m1000 = _run_single_condition(DEFAULT_CELL_PARAMS, 1000, 25)
        assert m1000["Pmax"] > m400["Pmax"]

    def test_fill_factor_reasonable(self):
        metrics = _run_single_condition(DEFAULT_CELL_PARAMS, 1000, 25)
        assert 0.5 < metrics["fill_factor"] < 0.9

    def test_zero_irradiance(self):
        metrics = _run_single_condition(DEFAULT_CELL_PARAMS, 0, 25)
        assert metrics["Pmax"] == 0 or metrics["Pmax"] < 0.01


# ---------------------------------------------------------------------------
# Experiment runner tests
# ---------------------------------------------------------------------------

class TestRunExperiment:
    def test_stc_baseline(self):
        result = run_experiment("stc_baseline", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.domain_name == "pv_iv"
        assert result.metrics["Voc"] > 0
        assert result.metrics["Pmax"] > 0
        assert result.metrics["fill_factor"] > 0
        assert result.duration_seconds >= 0

    def test_irradiance_sweep(self):
        result = run_experiment("irradiance_sweep", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert len(result.raw_data["sweep_results"]) == 6
        assert "irradiance_sensitivity" in result.metrics

    def test_temperature_sweep(self):
        result = run_experiment("temperature_sweep", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert len(result.raw_data["sweep_results"]) == 7
        assert "temp_coefficient_pmax" in result.metrics
        assert "temperature_sensitivity" in result.metrics
        # Temp coefficient should be negative for Si
        assert result.metrics["temp_coefficient_pmax"] < 0

    def test_combined_sensitivity(self):
        result = run_experiment("combined_sensitivity", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert len(result.raw_data["sweep_results"]) == 9  # 3 irr x 3 temp
        assert "combined_sensitivity" in result.metrics

    def test_unknown_template(self):
        with pytest.raises(ValueError, match="Unknown experiment template"):
            run_experiment("nonexistent", DEFAULT_CELL_PARAMS)

    def test_results_are_repeatable(self):
        r1 = run_experiment("stc_baseline", DEFAULT_CELL_PARAMS)
        r2 = run_experiment("stc_baseline", DEFAULT_CELL_PARAMS)
        assert r1.metrics["Voc"] == r2.metrics["Voc"]
        assert r1.metrics["Pmax"] == r2.metrics["Pmax"]
        assert r1.metrics["fill_factor"] == r2.metrics["fill_factor"]


# ---------------------------------------------------------------------------
# Physical plausibility tests
# ---------------------------------------------------------------------------

class TestPhysicalPlausibility:
    def test_default_params_plausible(self):
        ok, reasons = check_physical_plausibility(DEFAULT_CELL_PARAMS)
        assert ok is True
        assert len(reasons) == 0

    def test_negative_rs_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, R_s=-1)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False
        assert any("R_s" in r for r in reasons)

    def test_zero_rsh_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, R_sh_ref=0)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False

    def test_implausible_photocurrent_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, I_L_ref=100)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False

    def test_implausible_rs_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, R_s=50)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False


class TestMetricsPlausibility:
    def test_stc_metrics_plausible(self):
        result = run_experiment("stc_baseline", DEFAULT_CELL_PARAMS)
        ok, reasons = check_metrics_plausibility(result.metrics)
        assert ok is True

    def test_over_sq_rejected(self):
        metrics = {"efficiency": 40.0, "fill_factor": 0.8, "Voc": 30}
        ok, reasons = check_metrics_plausibility(metrics)
        assert ok is False
        assert any("Shockley-Queisser" in r for r in reasons)

    def test_negative_efficiency_rejected(self):
        metrics = {"efficiency": -5.0, "fill_factor": 0.5, "Voc": 10}
        ok, reasons = check_metrics_plausibility(metrics)
        assert ok is False

    def test_implausible_ff_rejected(self):
        metrics = {"efficiency": 20.0, "fill_factor": 0.95, "Voc": 30}
        ok, reasons = check_metrics_plausibility(metrics)
        assert ok is False


# ---------------------------------------------------------------------------
# Parameter variation tests (scientific correctness)
# ---------------------------------------------------------------------------

class TestParameterVariations:
    def test_higher_series_resistance_lowers_ff(self):
        """Higher Rs should lower fill factor."""
        params_low_rs = dict(DEFAULT_CELL_PARAMS, R_s=0.2)
        params_high_rs = dict(DEFAULT_CELL_PARAMS, R_s=2.0)
        r_low = run_experiment("stc_baseline", params_low_rs)
        r_high = run_experiment("stc_baseline", params_high_rs)
        assert r_low.metrics["fill_factor"] > r_high.metrics["fill_factor"]

    def test_higher_shunt_resistance_improves_performance(self):
        """Higher Rsh should improve performance (less leakage)."""
        params_low_rsh = dict(DEFAULT_CELL_PARAMS, R_sh_ref=50)
        params_high_rsh = dict(DEFAULT_CELL_PARAMS, R_sh_ref=1000)
        r_low = run_experiment("stc_baseline", params_low_rsh)
        r_high = run_experiment("stc_baseline", params_high_rsh)
        assert r_high.metrics["Pmax"] >= r_low.metrics["Pmax"]

    def test_higher_photocurrent_increases_isc(self):
        """Higher I_L_ref should directly increase Isc."""
        params_low = dict(DEFAULT_CELL_PARAMS, I_L_ref=7.0)
        params_high = dict(DEFAULT_CELL_PARAMS, I_L_ref=12.0)
        r_low = run_experiment("stc_baseline", params_low)
        r_high = run_experiment("stc_baseline", params_high)
        assert r_high.metrics["Isc"] > r_low.metrics["Isc"]

    def test_lower_saturation_current_increases_voc(self):
        """Lower I_o_ref should increase Voc (better junction quality)."""
        params_high_io = dict(DEFAULT_CELL_PARAMS, I_o_ref=1e-8)
        params_low_io = dict(DEFAULT_CELL_PARAMS, I_o_ref=1e-12)
        r_high = run_experiment("stc_baseline", params_high_io)
        r_low = run_experiment("stc_baseline", params_low_io)
        assert r_low.metrics["Voc"] > r_high.metrics["Voc"]
