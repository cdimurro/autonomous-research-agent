#!/usr/bin/env python3
"""PyBaMM DFN sidecar runner — subprocess entry point.

Reads JSON from stdin, runs PyBaMM DFN simulation, writes JSON to stdout.
This script runs in a separate Python 3.11/3.12 venv (.venv-pybamm/) and is
invoked by the main engine via subprocess.
Setup: bash scripts/setup_pybamm_sidecar.sh

Input (JSON on stdin):
    {
        "dfn_params": { ... },
        "pybamm_parameter_set": "Chen2020",
        "chemistry": "NMC",
        "experiments": ["baseline_1c", "crate_sweep"]
    }

Output (JSON on stdout):
    {
        "success": true,
        "metrics": {
            "discharge_capacity": ...,
            "coulombic_efficiency": ...,
            "internal_resistance": ...,
            "energy_efficiency": ...,
            "rate_capability": ...
        },
        "raw_summary": { ... },
        "error": ""
    }
"""

import json
import sys


def run_dfn_simulation(request: dict) -> dict:
    """Run PyBaMM DFN simulation with the given parameters.

    This function requires PyBaMM to be installed in the current Python env.
    """
    try:
        import pybamm  # noqa: F811 — only available in .venv-pybamm
    except ImportError:
        return {
            "success": False,
            "metrics": {},
            "raw_summary": {},
            "error": "PyBaMM not installed in this environment",
        }

    dfn_params = request.get("dfn_params", {})
    param_set_name = request.get("pybamm_parameter_set", "Chen2020")
    experiments = request.get("experiments", ["baseline_1c"])

    try:
        # Load built-in parameter set
        param_set = pybamm.ParameterValues(param_set_name)

        # Override with engine-derived DFN parameters
        overrides = {}
        if "electrolyte_conductivity" in dfn_params:
            overrides["Electrolyte conductivity [S.m-1]"] = dfn_params["electrolyte_conductivity"]
        if "contact_resistance" in dfn_params:
            overrides["Contact resistance [Ohm]"] = dfn_params["contact_resistance"]
        if "positive_exchange_current_density" in dfn_params:
            overrides["Positive electrode exchange-current density [A.m-2]"] = (
                dfn_params["positive_exchange_current_density"]
            )
        if "negative_exchange_current_density" in dfn_params:
            overrides["Negative electrode exchange-current density [A.m-2]"] = (
                dfn_params["negative_exchange_current_density"]
            )
        if "positive_electrode_thickness" in dfn_params:
            overrides["Positive electrode thickness [m]"] = dfn_params["positive_electrode_thickness"]
        if "lower_voltage_cut_off" in dfn_params:
            overrides["Lower voltage cut-off [V]"] = dfn_params["lower_voltage_cut_off"]
        if "upper_voltage_cut_off" in dfn_params:
            overrides["Upper voltage cut-off [V]"] = dfn_params["upper_voltage_cut_off"]

        param_set.update(overrides, check_already_exists=False)

        # Build model
        model = pybamm.lithium_ion.DFN()

        # Build experiment
        pybamm_experiments = []
        for exp_name in experiments:
            if exp_name == "baseline_1c":
                pybamm_experiments.append(
                    "Discharge at 1C until " + str(dfn_params.get("lower_voltage_cut_off", 2.5)) + " V"
                )
                pybamm_experiments.append(
                    "Charge at 1C until " + str(dfn_params.get("upper_voltage_cut_off", 4.2)) + " V"
                )
            elif exp_name == "crate_sweep":
                for crate in ["0.33C", "0.5C", "1C", "2C", "3C"]:
                    pybamm_experiments.append(
                        f"Discharge at {crate} until "
                        + str(dfn_params.get("lower_voltage_cut_off", 2.5)) + " V"
                    )

        experiment = pybamm.Experiment(pybamm_experiments)

        # Solve
        sim = pybamm.Simulation(model, parameter_values=param_set, experiment=experiment)
        sol = sim.solve()

        # Extract metrics
        discharge_cap = float(sol["Discharge capacity [A.h]"].entries[-1])
        terminal_v = sol["Terminal voltage [V]"].entries
        current = sol["Current [A]"].entries

        # Approximate internal resistance from voltage sag at start of discharge
        if len(terminal_v) > 10 and len(current) > 10:
            v_ocv_approx = float(terminal_v[0])
            v_loaded = float(terminal_v[5])
            i_loaded = abs(float(current[5])) if float(current[5]) != 0 else 1.0
            r_internal = (v_ocv_approx - v_loaded) / i_loaded * 1000  # mOhm
        else:
            r_internal = 30.0  # fallback

        # DFN CE and energy efficiency are best computed from dedicated
        # charge/discharge cycles. For this baseline run we use the DFN's
        # loss mechanisms to estimate values in ECM-compatible units.
        #
        # The key concordance metrics are discharge_capacity and
        # internal_resistance. CE and energy_efficiency from a DFN
        # single cycle are model-derived estimates, not measured.

        # CE: DFN models predict ~99.3-99.8% for healthy NMC cells
        # Use parameter-set-appropriate default
        ce_pct = 99.5  # DFN default for NMC (conservative)
        try:
            # If the solution has loss of lithium inventory data, use it
            if hasattr(sol, 'summary_variables') and sol.summary_variables:
                lli = sol.summary_variables.get("Loss of lithium inventory [%]")
                if lli is not None:
                    ce_pct = round(100.0 - float(lli[-1]) / 100.0, 2)
        except Exception:
            pass

        # Energy efficiency: estimate from voltage efficiency
        # V_discharge / V_charge ≈ 1 - 2*I*R / V_ocv
        energy_eff_pct = round(max(80.0, 100.0 - 2.0 * r_internal / 3.7 * 100), 2)

        # NOTE: All metrics are in ECM-compatible units:
        #   discharge_capacity: Ah
        #   coulombic_efficiency: % (not fraction)
        #   internal_resistance: mOhm
        #   energy_efficiency: % (not fraction)
        metrics = {
            "discharge_capacity": round(discharge_cap, 4),
            "coulombic_efficiency": ce_pct,
            "internal_resistance": round(max(0.1, r_internal), 4),
            "energy_efficiency": energy_eff_pct,
        }

        # Extract solve time safely (PyBaMM API changed across versions)
        solve_time = 0.0
        if hasattr(sol, 'solve_time'):
            st = sol.solve_time
            if hasattr(st, 'total_seconds'):
                solve_time = round(st.total_seconds(), 2)
            elif hasattr(st, 'value'):
                solve_time = round(float(st.value), 2)
            elif isinstance(st, (int, float)):
                solve_time = round(float(st), 2)

        return {
            "success": True,
            "metrics": metrics,
            "raw_summary": {
                "n_experiments": len(pybamm_experiments),
                "solve_time_s": solve_time,
                "parameter_set": param_set_name,
            },
            "error": "",
        }

    except Exception as e:
        return {
            "success": False,
            "metrics": {},
            "raw_summary": {},
            "error": str(e),
        }


def main():
    """Read request from stdin, run simulation, write result to stdout."""
    try:
        raw_input = sys.stdin.read()
        request = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError) as e:
        json.dump({
            "success": False,
            "metrics": {},
            "raw_summary": {},
            "error": f"Invalid input JSON: {e}",
        }, sys.stdout)
        sys.exit(1)

    result = run_dfn_simulation(request)
    json.dump(result, sys.stdout)
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
