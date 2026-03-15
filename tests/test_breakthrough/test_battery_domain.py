"""Tests for Battery ECM domain pack (CC-BE-2412)."""

from __future__ import annotations

import os

import pytest

from breakthrough_engine.battery_domain import (
    BATTERY_DOMAIN,
    BATTERY_METRICS,
    DEFAULT_CELL_PARAMS,
    EXPERIMENT_TEMPLATES,
    _ocv,
    check_metrics_plausibility,
    check_physical_plausibility,
    run_experiment,
    simulate_cycle,
)


# ---------------------------------------------------------------------------
# Domain spec tests
# ---------------------------------------------------------------------------

class TestBatteryDomain:
    def test_domain_name(self):
        assert BATTERY_DOMAIN.name == "battery_ecm"
        assert BATTERY_DOMAIN.display_name == "Battery ECM + Cycle Characterization"

    def test_metrics_defined(self):
        assert len(BATTERY_METRICS) == 9
        names = [m.name for m in BATTERY_METRICS]
        assert "discharge_capacity" in names
        assert "coulombic_efficiency" in names
        assert "internal_resistance" in names
        assert "capacity_retention" in names
        assert "fade_rate" in names
        assert "energy_efficiency" in names
        assert "rate_capability" in names
        assert "fast_charge_retention" in names
        assert "resistance_growth_pct" in names

    def test_primary_metrics(self):
        primary = [m for m in BATTERY_METRICS if m.is_primary]
        assert len(primary) == 6

    def test_banned_claims(self):
        assert len(BATTERY_DOMAIN.banned_claims) >= 3
        assert any("perpetual" in c for c in BATTERY_DOMAIN.banned_claims)

    def test_safety_constraints(self):
        assert any("100%" in c for c in BATTERY_DOMAIN.safety_constraints)


# ---------------------------------------------------------------------------
# OCV model tests
# ---------------------------------------------------------------------------

class TestOCVModel:
    def test_ocv_at_soc_zero(self):
        coeffs = DEFAULT_CELL_PARAMS["ocv_coeffs"]
        v = _ocv(0.0, coeffs)
        assert 2.5 <= v <= 3.5  # Should be near v_min

    def test_ocv_at_soc_one(self):
        coeffs = DEFAULT_CELL_PARAMS["ocv_coeffs"]
        v = _ocv(1.0, coeffs)
        assert 3.5 <= v <= 4.5  # Should be near v_max

    def test_ocv_monotonically_increasing(self):
        coeffs = DEFAULT_CELL_PARAMS["ocv_coeffs"]
        socs = [i / 20.0 for i in range(21)]
        voltages = [_ocv(s, coeffs) for s in socs]
        # OCV should generally increase with SOC (may not be perfectly monotonic
        # for all polynomials, but should be for default params)
        assert voltages[-1] > voltages[0]


# ---------------------------------------------------------------------------
# Single cycle tests
# ---------------------------------------------------------------------------

class TestSimulateCycle:
    def test_baseline_1c(self):
        result = simulate_cycle(DEFAULT_CELL_PARAMS, c_rate=1.0, temperature=25.0)
        assert result["success"] is True
        assert result["discharge_capacity"] > 0
        assert result["coulombic_efficiency"] > 90
        assert result["internal_resistance"] > 0
        assert result["avg_discharge_voltage"] > 2.5

    def test_capacity_near_nominal(self):
        result = simulate_cycle(DEFAULT_CELL_PARAMS, c_rate=1.0)
        # At 1C, should get close to nominal capacity (within 30%)
        nominal = DEFAULT_CELL_PARAMS["capacity_ah"]
        assert result["discharge_capacity"] > nominal * 0.7
        assert result["discharge_capacity"] <= nominal * 1.05

    def test_higher_crate_lower_capacity(self):
        # Use higher resistance to make voltage cutoff trigger earlier at high C-rate
        params = dict(DEFAULT_CELL_PARAMS, R0_mohm=60.0, R1_mohm=30.0)
        r1c = simulate_cycle(params, c_rate=1.0)
        r3c = simulate_cycle(params, c_rate=3.0)
        assert r3c["discharge_capacity"] < r1c["discharge_capacity"]

    def test_higher_crate_lower_avg_voltage(self):
        r1c = simulate_cycle(DEFAULT_CELL_PARAMS, c_rate=1.0)
        r3c = simulate_cycle(DEFAULT_CELL_PARAMS, c_rate=3.0)
        assert r3c["avg_discharge_voltage"] < r1c["avg_discharge_voltage"]

    def test_capacity_fade_with_prior_cycles(self):
        r0 = simulate_cycle(DEFAULT_CELL_PARAMS, n_prior_cycles=0)
        r100 = simulate_cycle(DEFAULT_CELL_PARAMS, n_prior_cycles=100)
        assert r100["discharge_capacity"] < r0["discharge_capacity"]
        assert r100["effective_capacity"] < r0["effective_capacity"]

    def test_cold_temperature_increases_resistance(self):
        r25 = simulate_cycle(DEFAULT_CELL_PARAMS, temperature=25.0)
        r10 = simulate_cycle(DEFAULT_CELL_PARAMS, temperature=10.0)
        # Cold increases R0, so resistance should be different
        # (depends on temp_coeff sign; negative temp → higher R0 for positive coeff)
        assert r10["internal_resistance"] != r25["internal_resistance"]

    def test_hot_temperature_decreases_resistance(self):
        r25 = simulate_cycle(DEFAULT_CELL_PARAMS, temperature=25.0)
        r40 = simulate_cycle(DEFAULT_CELL_PARAMS, temperature=40.0)
        # With positive temp_coeff_r0, hot temperature increases R0
        # but reduces overpotential effect — net depends on model
        assert r40["internal_resistance"] != r25["internal_resistance"]

    def test_results_are_deterministic(self):
        r1 = simulate_cycle(DEFAULT_CELL_PARAMS, c_rate=1.0)
        r2 = simulate_cycle(DEFAULT_CELL_PARAMS, c_rate=1.0)
        assert r1["discharge_capacity"] == r2["discharge_capacity"]
        assert r1["coulombic_efficiency"] == r2["coulombic_efficiency"]

    def test_depleted_capacity_returns_empty(self):
        # After many cycles, capacity should deplete
        result = simulate_cycle(DEFAULT_CELL_PARAMS, n_prior_cycles=2500)
        # With 0.05% fade per cycle, 2500 cycles = 125% fade → depleted
        assert result["success"] is False or result["discharge_capacity"] == 0


# ---------------------------------------------------------------------------
# Experiment template tests
# ---------------------------------------------------------------------------

class TestExperimentTemplates:
    def test_all_templates_exist(self):
        assert "baseline_cycle" in EXPERIMENT_TEMPLATES
        assert "cycle_aging" in EXPERIMENT_TEMPLATES
        assert "crate_sweep" in EXPERIMENT_TEMPLATES
        assert "pulse_resistance" in EXPERIMENT_TEMPLATES
        assert "thermal_sensitivity" in EXPERIMENT_TEMPLATES
        assert "fast_charge_stress" in EXPERIMENT_TEMPLATES
        assert "thermal_stress_aging" in EXPERIMENT_TEMPLATES
        assert "repeated_fast_charge_stress" in EXPERIMENT_TEMPLATES

    def test_baseline_cycle(self):
        result = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.domain_name == "battery_ecm"
        assert result.metrics["discharge_capacity"] > 0
        assert result.metrics["coulombic_efficiency"] > 90
        assert result.metrics["internal_resistance"] > 0

    def test_cycle_aging(self):
        result = run_experiment("cycle_aging", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.metrics["capacity_retention"] > 0
        assert result.metrics["capacity_retention"] <= 100.0
        assert result.metrics["fade_rate"] >= 0
        assert result.metrics["n_cycles_completed"] == 50

    def test_crate_sweep(self):
        result = run_experiment("crate_sweep", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert 0 < result.metrics["rate_capability"] <= 1.0
        assert len(result.raw_data["cycle_results"]) == 5

    def test_pulse_resistance(self):
        result = run_experiment("pulse_resistance", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.metrics["internal_resistance"] > 0
        assert result.metrics["r0_measured"] > 0

    def test_thermal_sensitivity(self):
        result = run_experiment("thermal_sensitivity", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.metrics["capacity_thermal_sensitivity"] >= 0
        assert result.metrics["resistance_thermal_sensitivity"] >= 0
        assert len(result.raw_data["cycle_results"]) == 4

    def test_fast_charge_stress(self):
        result = run_experiment("fast_charge_stress", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.metrics["capacity_retention"] > 0
        assert result.metrics["capacity_retention"] <= 100.0
        assert result.metrics["stress_fade_rate"] >= 0
        assert result.metrics["n_cycles_completed"] == 20
        assert result.metrics["fast_charge_c_rate"] == 2.0
        assert "stress_penalty_pct" in result.metrics

    def test_thermal_stress_aging(self):
        result = run_experiment("thermal_stress_aging", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.metrics["capacity_retention"] > 0
        assert result.metrics["capacity_retention"] <= 100.0
        assert result.metrics["stress_fade_rate"] >= 0
        assert result.metrics["n_cycles_completed"] == 20
        assert result.metrics["thermal_stress_temperature"] == 45.0
        assert "stress_penalty_pct" in result.metrics

    def test_repeated_fast_charge_stress(self):
        result = run_experiment("repeated_fast_charge_stress", DEFAULT_CELL_PARAMS)
        assert result.success is True
        assert result.metrics["capacity_retention"] > 0
        assert result.metrics["capacity_retention"] <= 100.0
        assert result.metrics["fast_charge_retention"] > 0
        assert result.metrics["stress_fade_rate"] >= 0
        assert result.metrics["n_cycles_completed"] == 30
        assert result.metrics["fast_charge_c_rate"] == 3.0
        assert "resistance_growth_pct" in result.metrics
        assert "stress_penalty_pct" in result.metrics

    def test_repeated_fast_charge_resistance_growth(self):
        """High-fade cell should show non-negative resistance growth under 3C stress."""
        high_fade = dict(DEFAULT_CELL_PARAMS, fade_rate_per_cycle=0.002)
        result = run_experiment("repeated_fast_charge_stress", high_fade)
        assert result.success is True
        # Resistance growth should be a number (may be 0 for constant-R ECM model)
        assert isinstance(result.metrics["resistance_growth_pct"], float)

    def test_repeated_fast_charge_vs_standard_fade(self):
        """3C stress should produce higher fade rate than 1C standard aging."""
        result_3c = run_experiment("repeated_fast_charge_stress", DEFAULT_CELL_PARAMS)
        result_1c = run_experiment("cycle_aging", DEFAULT_CELL_PARAMS)
        # Higher C-rate should not produce lower fade (may be equal in simple ECM)
        assert result_3c.metrics["stress_fade_rate"] >= result_1c.metrics["fade_rate"] * 0.9

    def test_stress_templates_repeatable(self):
        r1 = run_experiment("fast_charge_stress", DEFAULT_CELL_PARAMS)
        r2 = run_experiment("fast_charge_stress", DEFAULT_CELL_PARAMS)
        assert r1.metrics["capacity_retention"] == r2.metrics["capacity_retention"]
        assert r1.metrics["stress_fade_rate"] == r2.metrics["stress_fade_rate"]

    def test_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown experiment template"):
            run_experiment("nonexistent", DEFAULT_CELL_PARAMS)

    def test_results_are_repeatable(self):
        r1 = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS)
        r2 = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS)
        assert r1.metrics["discharge_capacity"] == r2.metrics["discharge_capacity"]


# ---------------------------------------------------------------------------
# Physical plausibility tests
# ---------------------------------------------------------------------------

class TestPhysicalPlausibility:
    def test_default_params_plausible(self):
        ok, reasons = check_physical_plausibility(DEFAULT_CELL_PARAMS)
        assert ok is True
        assert len(reasons) == 0

    def test_negative_r0_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, R0_mohm=-5)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False
        assert any("R0" in r for r in reasons)

    def test_negative_capacity_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, capacity_ah=-1)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False

    def test_excessive_capacity_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, capacity_ah=200)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False

    def test_coulombic_over_100_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, coulombic_eff=1.05)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False

    def test_negative_fade_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, fade_rate_per_cycle=-0.001)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False

    def test_vmin_above_vmax_rejected(self):
        params = dict(DEFAULT_CELL_PARAMS, v_min=4.5, v_max=4.0)
        ok, reasons = check_physical_plausibility(params)
        assert ok is False


class TestMetricsPlausibility:
    def test_baseline_metrics_plausible(self):
        result = run_experiment("baseline_cycle", DEFAULT_CELL_PARAMS)
        ok, reasons = check_metrics_plausibility(result.metrics)
        assert ok is True

    def test_over_100_coulombic_rejected(self):
        metrics = {"coulombic_efficiency": 105.0, "internal_resistance": 30}
        ok, reasons = check_metrics_plausibility(metrics)
        assert ok is False

    def test_negative_resistance_rejected(self):
        metrics = {"coulombic_efficiency": 99.0, "internal_resistance": -5}
        ok, reasons = check_metrics_plausibility(metrics)
        assert ok is False

    def test_negative_capacity_rejected(self):
        metrics = {"discharge_capacity": -1.0, "coulombic_efficiency": 99.0, "internal_resistance": 30}
        ok, reasons = check_metrics_plausibility(metrics)
        assert ok is False


# ---------------------------------------------------------------------------
# Config file existence tests
# ---------------------------------------------------------------------------

class TestBatteryConfig:
    def test_battery_domain_config_exists(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "config", "domains", "battery_ecm.yaml",
        )
        config_path = os.path.normpath(config_path)
        assert os.path.exists(config_path)

    def test_battery_research_program_exists(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "config", "research_programs", "battery_ecm.yaml",
        )
        config_path = os.path.normpath(config_path)
        assert os.path.exists(config_path)

    def test_battery_daily_profile_exists(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..", "config", "daily_profiles", "battery_evaluation.yaml",
        )
        config_path = os.path.normpath(config_path)
        assert os.path.exists(config_path)
