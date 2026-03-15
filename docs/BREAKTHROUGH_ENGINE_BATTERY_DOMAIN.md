# Battery ECM Domain — Hardened Benchmark

**Status:** Stable benchmark domain — regression-grade proving ground alongside PV

## What Battery Is

Equivalent-circuit and cycle characterization of a single Li-ion cell using a
Thevenin ECM (R0 + R1/C1) with empirical capacity-fade. All simulation runs
locally using numpy/scipy. No external API keys required.

## What Battery Is NOT

- Atomistic materials discovery or cathode chemistry invention
- Full electrochemical PDE simulation (Newman, P2D)
- Pack-scale thermal modeling
- Autonomous publication workflow
- Multi-cell or module-level simulation

## Why This Scope

The PV loop proved the domain-loop architecture: fixed candidates, fixed
experiments, fixed scorecard, conservative promotion, memory reuse. Battery
applies the same pattern to a slower, richer energy-storage domain at the
equivalent-circuit level — the simplest model that produces interpretable,
measurable, and comparable outputs.

## Simulation Model

**Thevenin ECM (1RC):**
- `R0` — ohmic resistance (mOhm)
- `R1` — polarization resistance (mOhm)
- `C1` — polarization capacitance (F)
- `capacity_ah` — nominal capacity (Ah)
- `ocv_coeffs` — OCV-SOC polynomial coefficients
- `coulombic_eff` — coulombic efficiency (0–1)
- `fade_rate_per_cycle` — capacity fade per cycle (fractional)
- `temp_coeff_r0` — temperature coefficient for R0

The model integrates V(t) = OCV(SOC) - I*R0 - V_RC during charge/discharge,
tracking SOC via coulomb counting with coulombic efficiency.

## Metrics

| Metric | Unit | Why It Matters |
|--------|------|---------------|
| `discharge_capacity` | Ah | Primary output — how much energy the cell delivers |
| `coulombic_efficiency` | % | Charge/discharge ratio — indicates side reactions |
| `internal_resistance` | mOhm | Ohmic + polarization — indicates power capability |
| `capacity_retention` | % | After N cycles — indicates longevity |
| `fade_rate` | %/cycle | Capacity loss rate — indicates degradation speed |
| `energy_efficiency` | % | Wh_out / Wh_in — round-trip efficiency |
| `rate_capability` | ratio | Capacity at high C-rate / capacity at low C-rate |

## Fixed Experiment Templates

1. **baseline_cycle** — 1C charge/discharge at 25C, extract basic metrics
2. **cycle_aging** — 50-cycle aging at 1C, track capacity retention and fade
3. **crate_sweep** — C/3, C/2, 1C, 2C, 3C discharge sweep, extract rate capability
4. **pulse_resistance** — 10s discharge pulse at 50% SOC for resistance characterization
5. **thermal_sensitivity** — Baseline cycle at 10C, 25C, 40C, 55C
6. **fast_charge_stress** — 20-cycle aging at 2C, measuring fast-charge fade penalty
7. **thermal_stress_aging** — 20-cycle aging at 1C/45C, measuring thermal degradation

## Candidate Families

Each family has bounded perturbation ranges, physical rationale, and documented
tradeoff risk.

- `reduced_resistance` — Lower R0/R1 (better contacts/electrolyte). Risk: thinner separator.
- `improved_capacity` — Higher capacity_ah (Si-graphite anode, high-Ni cathode). Risk: faster fade.
- `reduced_fade` — Lower fade_rate (electrolyte additives, ALD coatings). Risk: higher impedance.
- `improved_efficiency` — Higher coulombic_eff (reduced parasitic reactions). Risk: thermal sensitivity.
- `combined_moderate` — Modest multi-lever co-optimization. Risk: interaction effects.
- `bounded_aggressive` — Near-best-in-class parameters. Risk: requires advanced manufacturing.

Parameter ranges are grounded in published 18650/21700 datasheet values with 4
commercial cell references as anchors (Sony VTC6, Samsung 50E, Samsung 30Q, LG MJ1).

## Cross-Parameter Plausibility

6 checks reject physically contradictory parameter combinations at generation time:
1. Low R0 + high fade (stable interfaces don't degrade fast)
2. High capacity + low CE (thermal safety)
3. Low R0 + high R1 (inconsistent transport properties)
4. High capacity + low R0 (thick electrodes increase path length)
5. High fade + high CE (rapid fade implies side reactions)
6. Standard physical plausibility (positive values, bounded ranges)

## Hard Fail Gates

- Capacity retention < 50% after 50 cycles
- Coulombic efficiency < 90%
- Internal resistance > 200 mOhm
- Worst-case stress retention < 80%
- Stress resilience score < 0.40 (promotion gate)
- Negative capacity or efficiency
- Physically contradictory parameter combinations

## Scoring (8 components)

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| `capacity_retention` | 15% | Cycle life under standard aging |
| `coulombic_improvement` | 10% | CE vs baseline |
| `resistance_improvement` | 15% | R reduction vs baseline |
| `fade_improvement` | 10% | Fade rate reduction vs baseline |
| `rate_capability` | 10% | Capacity variation across C-rates |
| `robustness` | 10% | Worst-case capacity under all stress |
| `stress_resilience` | 15% | Fast-charge + thermal stress retention |
| `plausibility_penalty` | 15% | Metrics plausibility check |

## Memory Pattern

Two-phase memory-guided generation:
1. **IdeaMemory** — outcome-based: promoted families get higher weight, hard-fail
   families get down-ranked, all-rejected families get recovery tag
2. **ExperimentMemory** — weakness-based: families with repeated weakness get
   further down-weighted; stress-fragile families get `stress-informed` tag

Proposal tags: `[memory-supported]`, `[exploratory]`, `[recovery]`,
`[retry-with-correction]`, `[stress-informed]`

## Benchmark Mode

Battery is the second formal benchmark domain (after PV). Run with:

```bash
python -m breakthrough_engine battery benchmark --seed 42
```

The benchmark report (version 2) includes:
- Baseline metrics
- Best candidate with score, metrics, stress profile, and caveats
- Per-candidate breakdown with rejection reasons
- Held-out reference comparison (within envelope check)
- Stability indicators for regression detection

## Known Limitations (Intentionally Deferred)

- 1RC model only (no 2RC or distributed elements)
- Empirical fade model (not physics-based SEI growth)
- No calendar aging (only cycle aging)
- No state-of-health estimation
- No pack-level effects (thermal management, cell balancing)
- No cathode chemistry variation (fixed NMC assumed)
