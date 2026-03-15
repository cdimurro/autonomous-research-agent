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

### Battery ECM + Cycle (`battery_ecm`)

- **Model:** Thevenin ECM (1RC) + empirical capacity-fade
- **Metrics:** discharge_capacity, coulombic_efficiency, internal_resistance, capacity_retention
- **Templates:** baseline_cycle, cycle_aging, crate_sweep, pulse_resistance,
  thermal_sensitivity, fast_charge_stress, thermal_stress_aging
- **Families:** low_resistance, high_capacity, balanced, high_efficiency,
  aggressive, low_fade
- **Reference:** benchmark_nmc_21700_3200mah (held-out commercial NMC 21700)
- **Module:** `breakthrough_engine/battery_loop.py`, `breakthrough_engine/battery_domain.py`

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
python -m breakthrough_engine battery benchmark [--candidates N] [--threshold T] [--seed S]
python -m breakthrough_engine battery run [--candidates N] [--threshold T] [--seed S]
python -m breakthrough_engine battery dry-run [--candidates N] [--seed S]
python -m breakthrough_engine battery status
python -m breakthrough_engine battery memory
```

## Invariants

1. Max one promoted candidate per run
2. Optional alternate under strict conditions
3. Hard-fail gates reject unphysical parameter combinations
4. Held-out realism check against reference device required
5. All benchmark tests offline-safe (no API keys)
6. Memory must influence future proposals
7. Deterministic with fixed seed — same seed produces same report

## What Is Intentionally Deferred

- DC-DC converter optimization — comes after battery is proven
- Atomistic materials discovery — no cathode chemistry invention
- Pack-scale thermal simulation — single-cell only
- Multi-cell or module-level simulation
- Broad KG expansion beyond current domains
