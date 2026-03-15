"""PV I-V Characterization domain pack.

First narrow-domain optimization loop for Breakthrough Engine.
Uses pvlib for all PV modeling/simulation.
"""

from __future__ import annotations

import logging
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
# PV Domain Specification
# ---------------------------------------------------------------------------

PV_METRICS = [
    MetricSpec(name="Voc", unit="V", description="Open-circuit voltage", higher_is_better=True, is_primary=True),
    MetricSpec(name="Isc", unit="A", description="Short-circuit current", higher_is_better=True, is_primary=True),
    MetricSpec(name="Vmp", unit="V", description="Voltage at maximum power point", higher_is_better=True),
    MetricSpec(name="Imp", unit="A", description="Current at maximum power point", higher_is_better=True),
    MetricSpec(name="Pmax", unit="W", description="Maximum power output", higher_is_better=True, is_primary=True),
    MetricSpec(name="fill_factor", unit="", description="Fill factor (Pmax / (Voc * Isc))", lower_bound=0.0, upper_bound=1.0, higher_is_better=True, is_primary=True),
    MetricSpec(name="efficiency", unit="%", description="Power conversion efficiency", lower_bound=0.0, upper_bound=100.0, higher_is_better=True, is_primary=True),
]

PV_DOMAIN = DomainSpec(
    name="pv_iv",
    display_name="PV I-V Characterization",
    description="Photovoltaic current-voltage characterization using single-diode model via pvlib",
    metrics=PV_METRICS,
    banned_claims=[
        "perpetual motion",
        "over-unity device",
        "efficiency above Shockley-Queisser limit without multi-junction justification",
        "free energy",
    ],
    safety_constraints=[
        "Must not violate thermodynamic limits",
        "Efficiency must not exceed Shockley-Queisser limit for single-junction (~33.7%)",
        "All parameters must be physically realizable",
        "Series resistance must be non-negative",
        "Shunt resistance must be positive",
    ],
)

# ---------------------------------------------------------------------------
# Default cell parameters (typical crystalline Si)
# ---------------------------------------------------------------------------

DEFAULT_CELL_PARAMS = {
    "I_L_ref": 9.5,       # Photocurrent at reference (A)
    "I_o_ref": 1e-10,     # Diode saturation current (A)
    "R_s": 0.5,           # Series resistance (ohm)
    "R_sh_ref": 400.0,    # Shunt resistance (ohm)
    "a_ref": 1.5,         # Modified ideality factor (V)
    "alpha_sc": 0.003,    # Temp coeff of Isc (A/C)
    "N_s": 60,            # Number of cells in series
    "cell_area_cm2": 156.25,  # Cell area (cm2) — for efficiency calc
}

# ---------------------------------------------------------------------------
# Experiment templates
# ---------------------------------------------------------------------------

EXPERIMENT_TEMPLATES = {
    "stc_baseline": ExperimentTemplate(
        domain_name="pv_iv",
        name="stc_baseline",
        description="Standard Test Conditions: 1000 W/m2, 25C cell temp",
        parameters={"irradiance": 1000, "temperature": 25},
        expected_duration_seconds=1.0,
    ),
    "irradiance_sweep": ExperimentTemplate(
        domain_name="pv_iv",
        name="irradiance_sweep",
        description="Irradiance sweep from 200 to 1200 W/m2 at 25C",
        parameters={
            "irradiance_range": [200, 400, 600, 800, 1000, 1200],
            "temperature": 25,
        },
        expected_duration_seconds=5.0,
    ),
    "temperature_sweep": ExperimentTemplate(
        domain_name="pv_iv",
        name="temperature_sweep",
        description="Temperature sweep from 15C to 75C at 1000 W/m2",
        parameters={
            "irradiance": 1000,
            "temperature_range": [15, 25, 35, 45, 55, 65, 75],
        },
        expected_duration_seconds=5.0,
    ),
    "combined_sensitivity": ExperimentTemplate(
        domain_name="pv_iv",
        name="combined_sensitivity",
        description="Combined irradiance x temperature sensitivity matrix",
        parameters={
            "irradiance_range": [400, 700, 1000],
            "temperature_range": [25, 45, 65],
        },
        expected_duration_seconds=10.0,
    ),
}


# ---------------------------------------------------------------------------
# PV Experiment Runner (pvlib-backed)
# ---------------------------------------------------------------------------

def _run_single_condition(
    cell_params: dict,
    irradiance: float,
    temperature: float,
) -> dict:
    """Run single-diode model for one irradiance/temperature condition.

    Returns dict of extracted metrics.
    """
    # Zero irradiance produces no output
    if irradiance <= 0:
        return {
            "Voc": 0.0, "Isc": 0.0, "Vmp": 0.0, "Imp": 0.0,
            "Pmax": 0.0, "fill_factor": 0.0, "efficiency": 0.0,
            "irradiance": irradiance, "temperature": temperature,
        }

    try:
        from pvlib import pvsystem
    except ImportError:
        raise ImportError("pvlib is required for PV domain. Install with: pip install pvlib")

    params = pvsystem.calcparams_desoto(
        effective_irradiance=irradiance,
        temp_cell=temperature,
        alpha_sc=cell_params.get("alpha_sc", 0.003),
        a_ref=cell_params.get("a_ref", 1.5),
        I_L_ref=cell_params.get("I_L_ref", 9.5),
        I_o_ref=cell_params.get("I_o_ref", 1e-10),
        R_sh_ref=cell_params.get("R_sh_ref", 400.0),
        R_s=cell_params.get("R_s", 0.5),
    )

    result = pvsystem.singlediode(*params)

    voc = float(result["v_oc"])
    isc = float(result["i_sc"])
    vmp = float(result["v_mp"])
    imp = float(result["i_mp"])
    pmax = float(result["p_mp"])

    # Fill factor
    ff = pmax / (voc * isc) if (voc * isc) > 0 else 0.0

    # Efficiency: Pmax / (irradiance * cell_area)
    cell_area_m2 = cell_params.get("cell_area_cm2", 156.25) * 1e-4
    n_cells = cell_params.get("N_s", 60)
    total_area_m2 = cell_area_m2 * n_cells
    efficiency = (pmax / (irradiance * total_area_m2)) * 100.0 if irradiance > 0 else 0.0

    return {
        "Voc": round(voc, 4),
        "Isc": round(isc, 4),
        "Vmp": round(vmp, 4),
        "Imp": round(imp, 4),
        "Pmax": round(pmax, 4),
        "fill_factor": round(ff, 4),
        "efficiency": round(efficiency, 4),
        "irradiance": irradiance,
        "temperature": temperature,
    }


def run_experiment(
    template_name: str,
    cell_params: dict,
    template: Optional[ExperimentTemplate] = None,
) -> ExperimentRunResult:
    """Run a PV experiment template with given cell parameters.

    Returns ExperimentRunResult with metrics and raw sweep data.
    """
    import time

    if template is None:
        template = EXPERIMENT_TEMPLATES.get(template_name)
    if template is None:
        raise ValueError(f"Unknown experiment template: {template_name}")

    t0 = time.time()
    params = template.parameters
    raw_data: dict = {"conditions": [], "sweep_results": []}
    summary_metrics: dict = {}

    try:
        if template_name == "stc_baseline":
            metrics = _run_single_condition(
                cell_params,
                params["irradiance"],
                params["temperature"],
            )
            summary_metrics = metrics
            raw_data["conditions"] = [{"irradiance": params["irradiance"], "temperature": params["temperature"]}]
            raw_data["sweep_results"] = [metrics]

        elif template_name == "irradiance_sweep":
            sweep = []
            for irr in params["irradiance_range"]:
                m = _run_single_condition(cell_params, irr, params["temperature"])
                sweep.append(m)
            raw_data["conditions"] = [{"irradiance": irr, "temperature": params["temperature"]} for irr in params["irradiance_range"]]
            raw_data["sweep_results"] = sweep
            # Summary: STC point + sensitivity
            stc = next((s for s in sweep if s["irradiance"] == 1000), sweep[-1])
            summary_metrics = dict(stc)
            pmax_values = [s["Pmax"] for s in sweep]
            summary_metrics["irradiance_sensitivity"] = round(
                (max(pmax_values) - min(pmax_values)) / max(pmax_values) if max(pmax_values) > 0 else 0.0, 4
            )

        elif template_name == "temperature_sweep":
            sweep = []
            for temp in params["temperature_range"]:
                m = _run_single_condition(cell_params, params["irradiance"], temp)
                sweep.append(m)
            raw_data["conditions"] = [{"irradiance": params["irradiance"], "temperature": t} for t in params["temperature_range"]]
            raw_data["sweep_results"] = sweep
            stc = next((s for s in sweep if s["temperature"] == 25), sweep[0])
            summary_metrics = dict(stc)
            # Temperature coefficient of Pmax
            temps = [s["temperature"] for s in sweep]
            pmaxes = [s["Pmax"] for s in sweep]
            if len(temps) >= 2 and pmaxes[0] > 0:
                # Linear fit for temp coefficient (%/C)
                coeffs = np.polyfit(temps, pmaxes, 1)
                pmax_at_25 = next((s["Pmax"] for s in sweep if s["temperature"] == 25), pmaxes[0])
                temp_coeff = (coeffs[0] / pmax_at_25) * 100.0 if pmax_at_25 > 0 else 0.0
                summary_metrics["temp_coefficient_pmax"] = round(temp_coeff, 4)
            summary_metrics["temperature_sensitivity"] = round(
                (max(pmaxes) - min(pmaxes)) / max(pmaxes) if max(pmaxes) > 0 else 0.0, 4
            )

        elif template_name == "combined_sensitivity":
            sweep = []
            for irr in params["irradiance_range"]:
                for temp in params["temperature_range"]:
                    m = _run_single_condition(cell_params, irr, temp)
                    sweep.append(m)
            raw_data["conditions"] = [
                {"irradiance": irr, "temperature": t}
                for irr in params["irradiance_range"]
                for t in params["temperature_range"]
            ]
            raw_data["sweep_results"] = sweep
            stc = next(
                (s for s in sweep if s["irradiance"] == 1000 and s["temperature"] == 25),
                sweep[len(sweep) // 2],
            )
            summary_metrics = dict(stc)
            pmaxes = [s["Pmax"] for s in sweep]
            summary_metrics["combined_sensitivity"] = round(
                (max(pmaxes) - min(pmaxes)) / max(pmaxes) if max(pmaxes) > 0 else 0.0, 4
            )
        else:
            raise ValueError(f"Unsupported template: {template_name}")

        duration = time.time() - t0
        return ExperimentRunResult(
            candidate_id="",  # caller sets this
            template_id=template.id,
            domain_name="pv_iv",
            metrics=summary_metrics,
            raw_data=raw_data,
            duration_seconds=round(duration, 3),
            success=True,
        )

    except Exception as e:
        duration = time.time() - t0
        logger.error("PV experiment failed: %s", e)
        return ExperimentRunResult(
            candidate_id="",
            template_id=template.id if template else "",
            domain_name="pv_iv",
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
    """Check if cell parameters are physically plausible.

    Returns (is_plausible, list_of_reasons_if_not).
    """
    reasons = []

    if cell_params.get("R_s", 0) < 0:
        reasons.append("Series resistance (R_s) must be non-negative")

    if cell_params.get("R_sh_ref", 1) <= 0:
        reasons.append("Shunt resistance (R_sh_ref) must be positive")

    if cell_params.get("I_L_ref", 0) < 0:
        reasons.append("Photocurrent (I_L_ref) must be non-negative")

    if cell_params.get("I_o_ref", 0) < 0:
        reasons.append("Diode saturation current (I_o_ref) must be non-negative")

    if cell_params.get("a_ref", 0) <= 0:
        reasons.append("Ideality factor (a_ref) must be positive")

    # Physical bounds
    i_l = cell_params.get("I_L_ref", 9.5)
    if i_l > 50:
        reasons.append(f"Photocurrent {i_l}A implausibly high for a single cell")

    r_s = cell_params.get("R_s", 0.5)
    if r_s > 10:
        reasons.append(f"Series resistance {r_s} ohm implausibly high")

    a_ref = cell_params.get("a_ref", 1.5)
    if a_ref > 5:
        reasons.append(f"Ideality factor {a_ref} implausibly high (typical 1-2)")

    return len(reasons) == 0, reasons


def check_metrics_plausibility(metrics: dict) -> tuple[bool, list[str]]:
    """Check if experiment output metrics are physically plausible."""
    reasons = []

    eff = metrics.get("efficiency", 0)
    if eff > 33.7:
        reasons.append(f"Efficiency {eff}% exceeds Shockley-Queisser limit for single-junction")
    if eff < 0:
        reasons.append(f"Negative efficiency {eff}%")

    ff = metrics.get("fill_factor", 0)
    if ff > 0.9:
        reasons.append(f"Fill factor {ff} implausibly high (typical < 0.85)")
    if ff < 0.2 and ff > 0:
        reasons.append(f"Fill factor {ff} implausibly low")

    voc = metrics.get("Voc", 0)
    if voc < 0:
        reasons.append(f"Negative Voc {voc}V")
    if voc > 100:
        reasons.append(f"Voc {voc}V implausibly high for a single module")

    return len(reasons) == 0, reasons


# ---------------------------------------------------------------------------
# CEC module lookup
# ---------------------------------------------------------------------------

def get_cec_module(module_name: str) -> Optional[dict]:
    """Look up a module from the CEC database via pvlib.

    Returns dict of module parameters compatible with calcparams_desoto,
    or None if not found.
    """
    try:
        from pvlib import pvsystem
        modules = pvsystem.retrieve_sam("CECMod")
        if module_name in modules.columns:
            mod = modules[module_name]
            return {
                "I_L_ref": float(mod["I_L_ref"]),
                "I_o_ref": float(mod["I_o_ref"]),
                "R_s": float(mod["R_s"]),
                "R_sh_ref": float(mod["R_sh_ref"]),
                "a_ref": float(mod["a_ref"]),
                "alpha_sc": float(mod["alpha_sc"]),
                "N_s": int(mod["N_s"]),
                "cell_area_cm2": float(mod.get("A_c", 1.3)) * 10000 / int(mod["N_s"]),
                "cec_name": module_name,
                "technology": str(mod.get("Technology", "unknown")),
            }
        return None
    except Exception as e:
        logger.warning("CEC module lookup failed: %s", e)
        return None


def list_cec_modules(technology_filter: Optional[str] = None, limit: int = 20) -> list[str]:
    """List available CEC module names, optionally filtered by technology."""
    try:
        from pvlib import pvsystem
        modules = pvsystem.retrieve_sam("CECMod")
        if technology_filter:
            matching = []
            for col in modules.columns:
                tech = str(modules[col].get("Technology", ""))
                if technology_filter.lower() in tech.lower():
                    matching.append(col)
                    if len(matching) >= limit:
                        break
            return matching
        return list(modules.columns[:limit])
    except Exception as e:
        logger.warning("CEC module list failed: %s", e)
        return []
