"""Battery equivalent-circuit and cycle characterization domain pack.

Second narrow-domain optimization loop for Breakthrough Engine.
Uses a Thevenin ECM (R0 + R1/C1) with empirical capacity fade.
All simulation is local (numpy/scipy) — no external API keys.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

from .domain_models import (
    DomainSpec,
    ExperimentRunResult,
    ExperimentTemplate,
    MetricSpec,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Battery Domain Specification
# ---------------------------------------------------------------------------

BATTERY_METRICS = [
    MetricSpec(name="discharge_capacity", unit="Ah", description="Delivered discharge capacity",
               higher_is_better=True, is_primary=True),
    MetricSpec(name="coulombic_efficiency", unit="%", description="Charge/discharge coulombic efficiency",
               lower_bound=0.0, upper_bound=100.0, higher_is_better=True, is_primary=True),
    MetricSpec(name="internal_resistance", unit="mOhm", description="Total internal resistance (R0+R1)",
               higher_is_better=False, is_primary=True),
    MetricSpec(name="capacity_retention", unit="%", description="Capacity retention after cycling",
               lower_bound=0.0, upper_bound=100.0, higher_is_better=True, is_primary=True),
    MetricSpec(name="fade_rate", unit="%/cycle", description="Capacity fade rate per cycle",
               higher_is_better=False, is_primary=True),
    MetricSpec(name="energy_efficiency", unit="%", description="Round-trip energy efficiency (Wh_out/Wh_in)",
               lower_bound=0.0, upper_bound=100.0, higher_is_better=True),
    MetricSpec(name="rate_capability", unit="ratio", description="Capacity at high C-rate / capacity at low C-rate",
               lower_bound=0.0, upper_bound=1.0, higher_is_better=True),
]

BATTERY_DOMAIN = DomainSpec(
    name="battery_ecm",
    display_name="Battery ECM + Cycle Characterization",
    description=(
        "Li-ion cell equivalent-circuit and cycle characterization using "
        "Thevenin ECM (R0+R1/C1) with empirical capacity fade"
    ),
    metrics=BATTERY_METRICS,
    banned_claims=[
        "perpetual battery",
        "zero degradation over infinite cycles",
        "coulombic efficiency above 100%",
        "negative internal resistance",
        "capacity increasing with cycling without physical mechanism",
    ],
    safety_constraints=[
        "Coulombic efficiency must not exceed 100%",
        "Internal resistance must be positive",
        "Capacity must degrade or remain constant with cycling (no spontaneous capacity gain)",
        "Voltage must remain within safe cell limits (2.5V–4.2V for Li-ion)",
        "Capacity fade rate must be non-negative",
    ],
)

# ---------------------------------------------------------------------------
# Default cell parameters (typical NMC 18650 ~3Ah)
# ---------------------------------------------------------------------------

DEFAULT_CELL_PARAMS = {
    "capacity_ah": 3.0,          # Nominal capacity (Ah)
    "R0_mohm": 30.0,             # Ohmic resistance (mOhm)
    "R1_mohm": 15.0,             # Polarization resistance (mOhm)
    "C1_F": 500.0,               # Polarization capacitance (F)
    "v_min": 2.5,                # Minimum voltage (V)
    "v_max": 4.2,                # Maximum voltage (V)
    "coulombic_eff": 0.995,      # Coulombic efficiency
    "fade_rate_per_cycle": 0.0005,  # Capacity fade per cycle (fraction)
    "temp_coeff_r0": 0.003,      # R0 temperature coefficient (per degC from 25C)
    # OCV-SOC polynomial coefficients (V): OCV(SOC) = sum(c_i * SOC^i)
    # Fit for typical NMC: ~3.0V at SOC=0, ~4.15V at SOC=1
    "ocv_coeffs": [3.0, 1.5, -1.2, 0.85],
}


def _ocv(soc: float, coeffs: list[float]) -> float:
    """Compute open-circuit voltage from SOC using polynomial."""
    return sum(c * soc ** i for i, c in enumerate(coeffs))


def _docv_dsoc(soc: float, coeffs: list[float]) -> float:
    """Derivative of OCV w.r.t. SOC for numerical stability check."""
    return sum(i * c * soc ** max(0, i - 1) for i, c in enumerate(coeffs) if i > 0)


# ---------------------------------------------------------------------------
# Single-cycle simulation
# ---------------------------------------------------------------------------

def simulate_cycle(
    cell_params: dict,
    c_rate: float = 1.0,
    temperature: float = 25.0,
    n_prior_cycles: int = 0,
    dt: float = 1.0,
) -> dict:
    """Simulate one charge/discharge cycle using Thevenin ECM.

    Returns dict with cycle metrics and time-series data.
    """
    cap = cell_params.get("capacity_ah", 3.0)
    fade = cell_params.get("fade_rate_per_cycle", 0.0005)
    coul_eff = cell_params.get("coulombic_eff", 0.995)
    r0 = cell_params.get("R0_mohm", 30.0) / 1000.0  # Convert to Ohm
    r1 = cell_params.get("R1_mohm", 15.0) / 1000.0
    c1 = cell_params.get("C1_F", 500.0)
    v_min = cell_params.get("v_min", 2.5)
    v_max = cell_params.get("v_max", 4.2)
    temp_coeff = cell_params.get("temp_coeff_r0", 0.003)
    coeffs = cell_params.get("ocv_coeffs", [3.0, 1.5, -1.2, 0.85])

    # Apply capacity fade from prior cycling
    effective_cap = cap * (1.0 - fade * n_prior_cycles)
    if effective_cap <= 0:
        return _empty_cycle_result("Capacity depleted after cycling")

    # Temperature-dependent R0
    r0_eff = r0 * (1.0 + temp_coeff * (temperature - 25.0))
    r0_eff = max(r0_eff, 0.001)  # Floor at 1 mOhm

    current = c_rate * cap  # Discharge current (A)
    tau1 = r1 * c1  # RC time constant

    # --- Discharge phase ---
    soc = 1.0
    v_rc = 0.0  # RC element voltage
    discharge_ah = 0.0
    discharge_wh = 0.0
    discharge_voltages = []
    discharge_socs = []

    max_steps = int(2 * 3600 * cap / (current * dt)) + 100  # Safety limit
    for step in range(max_steps):
        ocv = _ocv(soc, coeffs)
        v_terminal = ocv - current * r0_eff - v_rc
        if v_terminal <= v_min or soc <= 0.0:
            break
        discharge_voltages.append(v_terminal)
        discharge_socs.append(soc)
        # Update SOC
        dsoc = (current * dt) / (effective_cap * 3600.0)
        soc -= dsoc
        soc = max(0.0, soc)
        # Update RC element (exponential relaxation)
        dv_rc = (current * r1 - v_rc) / tau1 * dt if tau1 > 0 else 0.0
        v_rc += dv_rc
        discharge_ah += current * dt / 3600.0
        discharge_wh += v_terminal * current * dt / 3600.0

    if not discharge_voltages:
        return _empty_cycle_result("No discharge data produced")

    # --- Charge phase (CC-CV simplified as CC to v_max) ---
    charge_current = current * coul_eff  # Charge is slightly less efficient
    charge_ah = 0.0
    charge_wh = 0.0
    v_rc = 0.0

    for step in range(max_steps):
        ocv = _ocv(soc, coeffs)
        v_terminal = ocv + charge_current * r0_eff + v_rc
        if v_terminal >= v_max or soc >= 1.0:
            break
        # Update SOC
        dsoc = (charge_current * dt) / (effective_cap * 3600.0)
        soc += dsoc
        soc = min(1.0, soc)
        # Update RC element
        dv_rc = (charge_current * r1 - v_rc) / tau1 * dt if tau1 > 0 else 0.0
        v_rc += dv_rc
        charge_ah += charge_current * dt / 3600.0
        charge_wh += v_terminal * charge_current * dt / 3600.0

    # Compute metrics
    coulombic = (discharge_ah / charge_ah * 100.0) if charge_ah > 0 else 0.0
    energy_eff = (discharge_wh / charge_wh * 100.0) if charge_wh > 0 else 0.0
    avg_v = sum(discharge_voltages) / len(discharge_voltages) if discharge_voltages else 0.0

    return {
        "discharge_capacity": round(discharge_ah, 4),
        "charge_capacity": round(charge_ah, 4),
        "coulombic_efficiency": round(min(coulombic, 100.0), 4),
        "energy_efficiency": round(min(energy_eff, 100.0), 4),
        "internal_resistance": round((r0_eff + r1) * 1000.0, 4),  # back to mOhm
        "avg_discharge_voltage": round(avg_v, 4),
        "min_discharge_voltage": round(min(discharge_voltages), 4),
        "effective_capacity": round(effective_cap, 4),
        "c_rate": c_rate,
        "temperature": temperature,
        "n_prior_cycles": n_prior_cycles,
        "n_discharge_points": len(discharge_voltages),
        "success": True,
        "error": "",
    }


def _empty_cycle_result(reason: str) -> dict:
    """Return an empty cycle result for failed simulations."""
    return {
        "discharge_capacity": 0.0,
        "charge_capacity": 0.0,
        "coulombic_efficiency": 0.0,
        "energy_efficiency": 0.0,
        "internal_resistance": 0.0,
        "avg_discharge_voltage": 0.0,
        "min_discharge_voltage": 0.0,
        "effective_capacity": 0.0,
        "c_rate": 0.0,
        "temperature": 25.0,
        "n_prior_cycles": 0,
        "n_discharge_points": 0,
        "success": False,
        "error": reason,
    }


# ---------------------------------------------------------------------------
# Experiment templates
# ---------------------------------------------------------------------------

EXPERIMENT_TEMPLATES = {
    "baseline_cycle": ExperimentTemplate(
        domain_name="battery_ecm",
        name="baseline_cycle",
        description="Single 1C charge/discharge cycle at 25C",
        parameters={"c_rate": 1.0, "temperature": 25.0},
        expected_duration_seconds=2.0,
    ),
    "cycle_aging": ExperimentTemplate(
        domain_name="battery_ecm",
        name="cycle_aging",
        description="50-cycle aging at 1C, tracking capacity retention and fade",
        parameters={"c_rate": 1.0, "temperature": 25.0, "n_cycles": 50},
        expected_duration_seconds=10.0,
    ),
    "crate_sweep": ExperimentTemplate(
        domain_name="battery_ecm",
        name="crate_sweep",
        description="Discharge at C/3, C/2, 1C, 2C, 3C to measure rate capability",
        parameters={"c_rates": [0.333, 0.5, 1.0, 2.0, 3.0], "temperature": 25.0},
        expected_duration_seconds=5.0,
    ),
    "pulse_resistance": ExperimentTemplate(
        domain_name="battery_ecm",
        name="pulse_resistance",
        description="10s discharge pulse at 50% SOC for resistance characterization",
        parameters={"pulse_c_rate": 2.0, "soc_target": 0.5, "temperature": 25.0},
        expected_duration_seconds=1.0,
    ),
    "thermal_sensitivity": ExperimentTemplate(
        domain_name="battery_ecm",
        name="thermal_sensitivity",
        description="Baseline cycle at 10C, 25C, 40C, 55C",
        parameters={"temperatures": [10.0, 25.0, 40.0, 55.0], "c_rate": 1.0},
        expected_duration_seconds=5.0,
    ),
    "fast_charge_stress": ExperimentTemplate(
        domain_name="battery_ecm",
        name="fast_charge_stress",
        description="20-cycle aging at 2C charge/discharge, measuring capacity fade under fast-charge stress",
        parameters={"c_rate": 2.0, "temperature": 25.0, "n_cycles": 20},
        expected_duration_seconds=8.0,
    ),
    "thermal_stress_aging": ExperimentTemplate(
        domain_name="battery_ecm",
        name="thermal_stress_aging",
        description="20-cycle aging at 1C at 45C, measuring accelerated thermal degradation",
        parameters={"c_rate": 1.0, "temperature": 45.0, "n_cycles": 20},
        expected_duration_seconds=8.0,
    ),
}


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def run_experiment(
    template_name: str,
    cell_params: dict,
    template: Optional[ExperimentTemplate] = None,
) -> ExperimentRunResult:
    """Run a battery experiment template with given cell parameters."""
    import time

    if template is None:
        template = EXPERIMENT_TEMPLATES.get(template_name)
    if template is None:
        raise ValueError(f"Unknown experiment template: {template_name}")

    t0 = time.time()
    params = template.parameters
    raw_data: dict = {"conditions": [], "cycle_results": []}
    summary_metrics: dict = {}

    try:
        if template_name == "baseline_cycle":
            result = simulate_cycle(
                cell_params,
                c_rate=params["c_rate"],
                temperature=params["temperature"],
            )
            if not result["success"]:
                raise RuntimeError(result["error"])
            summary_metrics = {
                "discharge_capacity": result["discharge_capacity"],
                "coulombic_efficiency": result["coulombic_efficiency"],
                "energy_efficiency": result["energy_efficiency"],
                "internal_resistance": result["internal_resistance"],
                "avg_discharge_voltage": result["avg_discharge_voltage"],
            }
            raw_data["conditions"] = [{"c_rate": params["c_rate"], "temperature": params["temperature"]}]
            raw_data["cycle_results"] = [result]

        elif template_name == "cycle_aging":
            n_cycles = params.get("n_cycles", 50)
            cycle_caps = []
            for i in range(n_cycles):
                result = simulate_cycle(
                    cell_params,
                    c_rate=params["c_rate"],
                    temperature=params["temperature"],
                    n_prior_cycles=i,
                )
                if not result["success"]:
                    break
                cycle_caps.append(result["discharge_capacity"])
                if i == 0 or i == n_cycles - 1 or i % 10 == 0:
                    raw_data["cycle_results"].append(result)

            if len(cycle_caps) < 2:
                raise RuntimeError("Cycle aging produced fewer than 2 valid cycles")

            initial_cap = cycle_caps[0]
            final_cap = cycle_caps[-1]
            retention = (final_cap / initial_cap * 100.0) if initial_cap > 0 else 0.0
            observed_fade = ((initial_cap - final_cap) / initial_cap / len(cycle_caps) * 100.0) if initial_cap > 0 else 0.0

            summary_metrics = {
                "capacity_retention": round(retention, 4),
                "fade_rate": round(observed_fade, 4),
                "initial_capacity": round(initial_cap, 4),
                "final_capacity": round(final_cap, 4),
                "n_cycles_completed": len(cycle_caps),
                "discharge_capacity": round(initial_cap, 4),
                "coulombic_efficiency": raw_data["cycle_results"][0].get("coulombic_efficiency", 0) if raw_data["cycle_results"] else 0,
                "internal_resistance": raw_data["cycle_results"][0].get("internal_resistance", 0) if raw_data["cycle_results"] else 0,
            }
            raw_data["conditions"] = [{"c_rate": params["c_rate"], "temperature": params["temperature"], "n_cycles": n_cycles}]

        elif template_name == "crate_sweep":
            sweep_results = []
            for c_rate in params["c_rates"]:
                result = simulate_cycle(
                    cell_params,
                    c_rate=c_rate,
                    temperature=params["temperature"],
                )
                sweep_results.append(result)
            raw_data["cycle_results"] = sweep_results
            raw_data["conditions"] = [{"c_rate": cr, "temperature": params["temperature"]} for cr in params["c_rates"]]

            caps = [r["discharge_capacity"] for r in sweep_results if r["success"]]
            if len(caps) >= 2 and caps[0] > 0:
                rate_capability = caps[-1] / caps[0]  # Highest C / lowest C
            else:
                rate_capability = 0.0

            # Use 1C result for baseline metrics
            one_c = next((r for r in sweep_results if abs(r["c_rate"] - 1.0) < 0.01 and r["success"]), sweep_results[0])
            summary_metrics = {
                "rate_capability": round(rate_capability, 4),
                "discharge_capacity": one_c["discharge_capacity"],
                "coulombic_efficiency": one_c["coulombic_efficiency"],
                "internal_resistance": one_c["internal_resistance"],
                "crate_sensitivity": round(1.0 - rate_capability, 4) if rate_capability > 0 else 1.0,
            }

        elif template_name == "pulse_resistance":
            # Simulate short pulse at target SOC
            r0 = cell_params.get("R0_mohm", 30.0)
            r1 = cell_params.get("R1_mohm", 15.0)
            temp_coeff = cell_params.get("temp_coeff_r0", 0.003)
            temp = params["temperature"]
            r0_eff = r0 * (1.0 + temp_coeff * (temp - 25.0))
            # For a 10s pulse, R1 partially activates depending on RC time constant
            c1 = cell_params.get("C1_F", 500.0)
            tau = r1 / 1000.0 * c1  # seconds
            pulse_duration = 10.0
            r1_effective = r1 * (1.0 - math.exp(-pulse_duration / tau)) if tau > 0 else r1
            total_pulse_r = r0_eff + r1_effective

            summary_metrics = {
                "internal_resistance": round(total_pulse_r, 4),
                "r0_measured": round(r0_eff, 4),
                "r1_effective": round(r1_effective, 4),
                "discharge_capacity": cell_params.get("capacity_ah", 3.0),
                "coulombic_efficiency": cell_params.get("coulombic_eff", 0.995) * 100.0,
            }
            raw_data["conditions"] = [{"pulse_c_rate": params["pulse_c_rate"], "soc": params["soc_target"], "temperature": temp}]
            raw_data["cycle_results"] = [summary_metrics]

        elif template_name == "thermal_sensitivity":
            sweep_results = []
            for temp in params["temperatures"]:
                result = simulate_cycle(
                    cell_params,
                    c_rate=params["c_rate"],
                    temperature=temp,
                )
                sweep_results.append(result)
            raw_data["cycle_results"] = sweep_results
            raw_data["conditions"] = [{"c_rate": params["c_rate"], "temperature": t} for t in params["temperatures"]]

            # Use 25C result as baseline
            t25 = next((r for r in sweep_results if abs(r["temperature"] - 25.0) < 1.0 and r["success"]), sweep_results[0])
            caps = [r["discharge_capacity"] for r in sweep_results if r["success"]]
            resistances = [r["internal_resistance"] for r in sweep_results if r["success"]]

            cap_sensitivity = ((max(caps) - min(caps)) / max(caps)) if caps and max(caps) > 0 else 0.0
            r_sensitivity = ((max(resistances) - min(resistances)) / max(resistances)) if resistances and max(resistances) > 0 else 0.0

            summary_metrics = {
                "discharge_capacity": t25["discharge_capacity"],
                "coulombic_efficiency": t25["coulombic_efficiency"],
                "internal_resistance": t25["internal_resistance"],
                "capacity_thermal_sensitivity": round(cap_sensitivity, 4),
                "resistance_thermal_sensitivity": round(r_sensitivity, 4),
            }

        elif template_name in ("fast_charge_stress", "thermal_stress_aging"):
            # Shared logic: cycle aging under stress conditions
            n_cycles = params.get("n_cycles", 20)
            stress_c_rate = params.get("c_rate", 2.0)
            stress_temp = params.get("temperature", 25.0)
            cycle_caps = []
            for i in range(n_cycles):
                result = simulate_cycle(
                    cell_params,
                    c_rate=stress_c_rate,
                    temperature=stress_temp,
                    n_prior_cycles=i,
                )
                if not result["success"]:
                    break
                cycle_caps.append(result["discharge_capacity"])
                if i == 0 or i == n_cycles - 1 or i % 5 == 0:
                    raw_data["cycle_results"].append(result)

            if len(cycle_caps) < 2:
                raise RuntimeError(f"{template_name} produced fewer than 2 valid cycles")

            initial_cap = cycle_caps[0]
            final_cap = cycle_caps[-1]
            retention = (final_cap / initial_cap * 100.0) if initial_cap > 0 else 0.0
            observed_fade = (
                (initial_cap - final_cap) / initial_cap / len(cycle_caps) * 100.0
            ) if initial_cap > 0 else 0.0

            # Compare to 1C/25C baseline to quantify stress penalty
            baseline_1c = simulate_cycle(cell_params, c_rate=1.0, temperature=25.0)
            baseline_cap = baseline_1c["discharge_capacity"] if baseline_1c["success"] else initial_cap
            stress_penalty = (
                (baseline_cap - initial_cap) / baseline_cap * 100.0
            ) if baseline_cap > 0 else 0.0

            summary_metrics = {
                "capacity_retention": round(retention, 4),
                "fade_rate": round(observed_fade, 4),
                "stress_fade_rate": round(observed_fade, 4),
                "initial_capacity": round(initial_cap, 4),
                "final_capacity": round(final_cap, 4),
                "n_cycles_completed": len(cycle_caps),
                "stress_penalty_pct": round(max(0.0, stress_penalty), 4),
                "discharge_capacity": round(initial_cap, 4),
                "coulombic_efficiency": (
                    raw_data["cycle_results"][0].get("coulombic_efficiency", 0)
                    if raw_data["cycle_results"] else 0
                ),
                "internal_resistance": (
                    raw_data["cycle_results"][0].get("internal_resistance", 0)
                    if raw_data["cycle_results"] else 0
                ),
            }
            if template_name == "fast_charge_stress":
                summary_metrics["fast_charge_c_rate"] = stress_c_rate
            else:
                summary_metrics["thermal_stress_temperature"] = stress_temp
            raw_data["conditions"] = [{
                "c_rate": stress_c_rate,
                "temperature": stress_temp,
                "n_cycles": n_cycles,
            }]

        else:
            raise ValueError(f"Unsupported template: {template_name}")

        duration = time.time() - t0
        return ExperimentRunResult(
            candidate_id="",
            template_id=template.id,
            domain_name="battery_ecm",
            metrics=summary_metrics,
            raw_data=raw_data,
            duration_seconds=round(duration, 3),
            success=True,
        )

    except Exception as e:
        duration = time.time() - t0
        logger.error("Battery experiment failed: %s", e)
        return ExperimentRunResult(
            candidate_id="",
            template_id=template.id if template else "",
            domain_name="battery_ecm",
            metrics={},
            raw_data={},
            duration_seconds=round(duration, 3),
            success=False,
            error_message=str(e),
        )


# ---------------------------------------------------------------------------
# Physical plausibility checks
# ---------------------------------------------------------------------------

def check_physical_plausibility(cell_params: dict) -> tuple[bool, list[str]]:
    """Check if battery cell parameters are physically plausible."""
    reasons = []

    cap = cell_params.get("capacity_ah", 3.0)
    if cap <= 0:
        reasons.append(f"Capacity must be positive, got {cap} Ah")
    if cap > 100:
        reasons.append(f"Capacity {cap} Ah implausibly high for a single cell")

    r0 = cell_params.get("R0_mohm", 30.0)
    if r0 < 0:
        reasons.append(f"R0 must be non-negative, got {r0} mOhm")
    if r0 > 500:
        reasons.append(f"R0 {r0} mOhm implausibly high")

    r1 = cell_params.get("R1_mohm", 15.0)
    if r1 < 0:
        reasons.append(f"R1 must be non-negative, got {r1} mOhm")
    if r1 > 200:
        reasons.append(f"R1 {r1} mOhm implausibly high")

    c1 = cell_params.get("C1_F", 500.0)
    if c1 <= 0:
        reasons.append(f"C1 must be positive, got {c1} F")

    coul = cell_params.get("coulombic_eff", 0.995)
    if coul > 1.0:
        reasons.append(f"Coulombic efficiency {coul} exceeds 100%")
    if coul < 0.5:
        reasons.append(f"Coulombic efficiency {coul*100:.1f}% implausibly low")

    fade = cell_params.get("fade_rate_per_cycle", 0.0005)
    if fade < 0:
        reasons.append(f"Fade rate must be non-negative, got {fade}")
    if fade > 0.05:
        reasons.append(f"Fade rate {fade*100:.1f}%/cycle implausibly high")

    v_min = cell_params.get("v_min", 2.5)
    v_max = cell_params.get("v_max", 4.2)
    if v_min >= v_max:
        reasons.append(f"v_min ({v_min}V) must be less than v_max ({v_max}V)")
    if v_min < 1.0:
        reasons.append(f"v_min {v_min}V below safe Li-ion cutoff")
    if v_max > 5.0:
        reasons.append(f"v_max {v_max}V above safe Li-ion limit")

    return len(reasons) == 0, reasons


def check_metrics_plausibility(metrics: dict) -> tuple[bool, list[str]]:
    """Check if battery experiment output metrics are physically plausible."""
    reasons = []

    coul = metrics.get("coulombic_efficiency", 0)
    if coul > 100.0:
        reasons.append(f"Coulombic efficiency {coul}% exceeds 100%")
    if 0 < coul < 80.0:
        reasons.append(f"Coulombic efficiency {coul}% implausibly low for Li-ion")

    ee = metrics.get("energy_efficiency", 0)
    if ee > 100.0:
        reasons.append(f"Energy efficiency {ee}% exceeds 100%")

    r = metrics.get("internal_resistance", 0)
    if r < 0:
        reasons.append(f"Internal resistance {r} mOhm is negative")
    if r > 500:
        reasons.append(f"Internal resistance {r} mOhm implausibly high for a single cell")

    cap = metrics.get("discharge_capacity", 0)
    if cap < 0:
        reasons.append(f"Discharge capacity {cap} Ah is negative")

    ret = metrics.get("capacity_retention", 0)
    if ret is not None and ret > 100.0:
        reasons.append(f"Capacity retention {ret}% exceeds 100% (spontaneous capacity gain)")

    return len(reasons) == 0, reasons
