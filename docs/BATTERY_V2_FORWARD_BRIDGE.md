# Battery v2 — Forward Bridge

**Status:** Design-only. Not implemented in this batch. Intentionally deferred.

## What Battery v2 Could Include

The current battery benchmark (v2) is a hardened ECM-based loop with
fast-charge and degradation awareness. The next stage of battery work
could deepen the domain in several directions:

### 1. Cathode-Focused Candidate Generation — IMPLEMENTED

Four cathode-focused candidate families with chemistry-anchored generation:

- `cathode_high_ni` (NMC-811/NCA) — literature-backed (Chen2020)
- `cathode_lfp` (LFP) — literature-backed (Prada2013)
- `cathode_lmfp` (LMFP) — heuristic (CATL M3P data)
- `cathode_nmc532` (NMC-532) — literature-backed (OKane2022)

Each profile carries `profile_source`, `profile_confidence`, and
`pybamm_parameter_set` metadata. Chemistry-specific base params are
used instead of DEFAULT_CELL_PARAMS, with perturbations on top.

New experiment template: `cathode_thermal_stability` (2C/55C, 15 cycles)
targeting high-Ni thermal failure mode. Included in robustness profile.

### 2. Richer Solver Path

Replace or augment the 1RC Thevenin ECM with:
- 2RC model (separate fast and slow polarization)
- Warburg impedance element for diffusion-limited behavior
- State-dependent resistance (R0 as function of SOC and temperature)

**Why deferred:** 1RC is sufficient for interpretable benchmarking.
2RC adds complexity without proportional gain at this stage.

### 3. Stronger Degradation Modeling

Replace empirical fade model with physics-based degradation:
- SEI growth (capacity loss + impedance rise)
- Lithium plating at high C-rates and low temperatures
- Active material loss (particle cracking)
- Calendar aging (time-dependent, not just cycle-dependent)

**Why deferred:** Physics-based degradation requires validated kinetic
parameters. Current empirical model is sufficient for candidate ranking
and is more interpretable.

### 4. PyBaMM Sidecar Integration — IMPLEMENTED

PyBaMM DFN verification runs as an isolated sidecar in a separate Python 3.12
venv (`.venv-pybamm/`), communicating via JSON-over-subprocess. The main engine
(Python 3.14) never imports PyBaMM.

**Architecture:**
- `breakthrough_engine/battery_sidecar.py` — adapter, mock, ECM-to-DFN mapping, concordance
- `battery_sidecar/pybamm_runner.py` — subprocess entry point
- Top-2 qualifying candidates verified through sidecar before promotion
- Concordance gate: `< 0.30` veto, `0.30–0.60` caveat, `> 0.60` confirmed
- Four result states: SUCCESS, UNAVAILABLE, ERROR, INVALID
- `MockPyBaMMSidecar` for offline-safe benchmarks
- CLI flags: `--no-sidecar`, `--mock-sidecar`

**Setup:**
```bash
python3.12 -m venv .venv-pybamm
.venv-pybamm/bin/pip install -r battery_sidecar/requirements.txt
```

### 5. Optional Omniverse Escalation

For candidates that pass the ECM benchmark, escalation to higher-fidelity
simulation via Omniverse could provide:
- Thermal-electrochemical coupled simulation
- Pack-level validation
- Manufacturing variability analysis

**Why deferred:** Omniverse integration is a separate initiative.
Battery v2 should remain self-contained and offline-safe.

## What Must Be Preserved

Any future battery v2 work must preserve:
- Current benchmark baseline comparability
- Offline-safe operation (no required API keys)
- Deterministic, seed-reproducible results
- Conservative promotion policy
- Memory-guided generation pattern
- Unified benchmark report contract
- PV domain stability

## Bridge Points

The current battery v2 benchmark provides these bridge points for
future cathode-focused work:
- `rate_optimized` family can be extended with cathode-specific parameters
- `resistance_growth_pct` metric directly relates to SEI growth
- `repeated_fast_charge_stress` template (3C/30 cycles) tests the regime
  most relevant to cathode degradation
- `degradation_profile` in benchmark report provides the comparison
  framework for physics-based degradation models
- Memory system tracks fast-charge-specific weaknesses, which would
  inform cathode-chemistry search direction
