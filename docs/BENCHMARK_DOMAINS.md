# Benchmark Domains

**Last Updated:** 2026-03-14

## Overview

Benchmark domains are narrow scientific optimization loops that serve as
regression-grade proving grounds for the Breakthrough Engine. Each domain
uses the shared contract layer (`domain_models.py`) and emits a unified
benchmark report.

## Current Domains

### PV I-V Characterization (`pv_iv`)

- **Model:** pvlib single-diode (5-parameter)
- **Metrics:** Voc, Isc, Pmax, fill_factor, efficiency
- **Templates:** stc_baseline, irradiance_sweep, temperature_sweep, combined_sensitivity
- **Families:** reduced_series_resistance, improved_junction_quality, enhanced_photocurrent,
  improved_shunt_resistance, combined_moderate, bounded_aggressive
- **Reference:** benchmark_mono_si_300w (held-out commercial mono-Si module)
- **Module:** `breakthrough_engine/pv_loop.py`, `breakthrough_engine/pv_domain.py`

### Battery ECM + Cycle (`battery_ecm`) — v2, Fast-Charge and Degradation-Aware

- **Model:** Thevenin ECM (1RC: R0 + R1/C1) + empirical capacity-fade
- **Metrics (9, 6 primary):**
  - *Primary:* discharge_capacity, coulombic_efficiency, internal_resistance,
    capacity_retention, fade_rate, fast_charge_retention
  - *Secondary:* energy_efficiency, rate_capability, resistance_growth_pct
- **Templates (8):** baseline_cycle, cycle_aging, crate_sweep, pulse_resistance,
  thermal_sensitivity, fast_charge_stress, thermal_stress_aging,
  repeated_fast_charge_stress (3C/30-cycle with resistance tracking)
- **Families (7):** reduced_resistance, improved_capacity, reduced_fade,
  improved_efficiency, combined_moderate, rate_optimized, bounded_aggressive
- **Tradeoff penalties:** improved_capacity incurs fade penalty; reduced_fade incurs R1 penalty
- **Cross-parameter plausibility:** 7 checks reject physically contradictory combinations
- **Reference:** benchmark_nmc_21700_3200mah (held-out commercial NMC 21700);
  parameter ranges anchored to 5 commercial cells (Sony VTC6, Samsung 50E,
  Samsung 30Q, LG MJ1, Molicel P42A)
- **Scoring (8 components):** capacity_retention, coulombic_improvement,
  resistance_improvement, fade_improvement, rate_capability, robustness,
  stress_resilience, plausibility_penalty
- **Hard-fail gates:** capacity retention <50%, CE <90%, resistance >200 mOhm,
  worst-case stress retention <80%, resistance growth >20%, stress resilience <0.40,
  regime-specificity imbalance, negative metrics, contradictory parameters
- **Benchmark report (v2):** includes degradation_profile, family_summary,
  best candidate rationale and caveats
- **Memory:** two-phase (outcome + weakness); battery-specific lessons for
  fast-charge degradation, resistance growth, and rate-tradeoff collapse
- **Baseline freeze:** `runtime/battery_loop/battery_baseline_v1_frozen.json`
- **Module:** `breakthrough_engine/battery_loop.py`, `breakthrough_engine/battery_domain.py`
- **Solver sidecar:** Optional PyBaMM DFN verification via isolated Python 3.12 venv.
  Top-2 qualifying candidates verified before promotion. Concordance gate:
  `< 0.30` veto, `0.30–0.60` caveat, `> 0.60` confirmed.
  Four result states: SUCCESS, UNAVAILABLE, ERROR, INVALID.
  CLI: `--no-sidecar`, `--mock-sidecar`.
  Module: `breakthrough_engine/battery_sidecar.py`
- **Forward bridge:** see [BATTERY_V2_FORWARD_BRIDGE.md](BATTERY_V2_FORWARD_BRIDGE.md)

## Unified Benchmark Report (v3)

Both domains emit reports with the same top-level structure. Required keys are
defined in `domain_models.BENCHMARK_REPORT_REQUIRED_KEYS`. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full schema.

## CLI Commands

```bash
# PV
python -m breakthrough_engine pv benchmark [--candidates N] [--threshold T] [--seed S]
python -m breakthrough_engine pv run [--candidates N] [--threshold T] [--seed S]
python -m breakthrough_engine pv dry-run [--candidates N] [--seed S]
python -m breakthrough_engine pv status
python -m breakthrough_engine pv memory

# Battery
python -m breakthrough_engine battery benchmark [--candidates N] [--threshold T] [--seed S] [--mock-sidecar] [--no-sidecar]
python -m breakthrough_engine battery run [--candidates N] [--threshold T] [--seed S] [--mock-sidecar] [--no-sidecar]
python -m breakthrough_engine battery dry-run [--candidates N] [--seed S]
python -m breakthrough_engine battery status
python -m breakthrough_engine battery memory
```

## Invariants

1. Max one promoted candidate per run
2. Optional alternate under strict conditions (different family, near-threshold)
3. Hard-fail gates reject unphysical parameter combinations
4. Held-out realism check against reference device required
5. All benchmark tests offline-safe (no API keys)
6. Memory must influence future proposals
7. Deterministic with fixed seed — same seed produces same report
8. Stress resilience gate for promotion (battery: >= 0.40)
9. Regime-specificity gate: no extreme component imbalance in score
10. Resistance growth hard-fail under fast-charge stress (battery: > 20%)

## What Is Intentionally Deferred

- DC-DC converter optimization — comes after battery is proven
- Atomistic materials discovery — no cathode chemistry invention
- Pack-scale thermal simulation — single-cell only
- Multi-cell or module-level simulation
- Broad KG expansion beyond current domains
