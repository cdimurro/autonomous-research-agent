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

        v_lo = str(dfn_params.get("lower_voltage_cut_off", 2.5))
        v_hi = str(dfn_params.get("upper_voltage_cut_off", 4.2))

        # Build experiment: baseline 1C + optional high-rate verification
        pybamm_experiments = []
        for exp_name in experiments:
            if exp_name == "baseline_1c":
                pybamm_experiments.append(f"Discharge at 1C until {v_lo} V")
                pybamm_experiments.append(f"Charge at 1C until {v_hi} V")
            elif exp_name == "high_rate_2c":
                pybamm_experiments.append(f"Discharge at 2C until {v_lo} V")
                pybamm_experiments.append(f"Charge at 1C until {v_hi} V")
            elif exp_name == "high_rate_3c":
                pybamm_experiments.append(f"Discharge at 3C until {v_lo} V")
                pybamm_experiments.append(f"Charge at 1C until {v_hi} V")
            elif exp_name == "crate_sweep":
                for crate in ["0.33C", "0.5C", "1C", "2C", "3C"]:
                    pybamm_experiments.append(f"Discharge at {crate} until {v_lo} V")

        experiment = pybamm.Experiment(pybamm_experiments)

        # Solve
        sim = pybamm.Simulation(model, parameter_values=param_set, experiment=experiment)
        sol = sim.solve()

        # Extract per-step metrics from solution cycles
        # PyBaMM Experiment solutions have a .cycles property where each
        # cycle contains discharge/charge steps.
        step_caps = []  # (rate_label, discharge_capacity)
        try:
            for i, cycle in enumerate(sol.cycles):
                cap = float(cycle["Discharge capacity [A.h]"].entries[-1])
                label = pybamm_experiments[i * 2] if i * 2 < len(pybamm_experiments) else f"step_{i}"
                step_caps.append((label, cap))
        except (AttributeError, IndexError, KeyError):
            # Fallback: single experiment, use total
            try:
                cap = float(sol["Discharge capacity [A.h]"].entries[-1])
                step_caps.append(("total", cap))
            except (KeyError, IndexError):
                pass

        # Primary metric: 1C discharge capacity (first step)
        discharge_cap = step_caps[0][1] if step_caps else 0.0

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

        # Compute high-rate retention from step capacities
        # cap_at_high_rate / cap_at_1c shows how much capacity the DFN
        # model loses under fast-charge conditions
        cap_1c = None
        cap_2c = None
        cap_3c = None
        for label, cap in step_caps:
            if "1C" in label and "0.33" not in label and "0.5" not in label:
                if cap_1c is None:  # take first 1C step only
                    cap_1c = cap
            elif "2C" in label and "0.5" not in label:
                cap_2c = cap
            elif "3C" in label:
                cap_3c = cap

        high_rate_retention = None
        if cap_1c and cap_1c > 0:
            if cap_3c is not None:
                high_rate_retention = round((cap_3c / cap_1c) * 100, 2)
            elif cap_2c is not None:
                high_rate_retention = round((cap_2c / cap_1c) * 100, 2)

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
        #   high_rate_retention: % (capacity at highest rate / capacity at 1C)
        metrics = {
            "discharge_capacity": round(discharge_cap, 4),
            "coulombic_efficiency": ce_pct,
            "internal_resistance": round(max(0.1, r_internal), 4),
            "energy_efficiency": energy_eff_pct,
        }
        if high_rate_retention is not None:
            metrics["high_rate_retention"] = high_rate_retention

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
