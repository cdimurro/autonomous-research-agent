# Battery ECM Domain — v1 Scope

**Status:** Active — second narrow domain after PV

## What Battery v1 Is

Equivalent-circuit and cycle characterization of a single Li-ion cell using a
Thevenin ECM (R0 + R1/C1) with empirical capacity-fade. All simulation runs
locally using numpy/scipy. No external API keys required.

## What Battery v1 Is NOT

- Atomistic materials discovery or cathode chemistry invention
- Full electrochemical PDE simulation (Newman, P2D)
- Pack-scale thermal modeling
- Autonomous publication workflow
- Multi-cell or module-level simulation

## Why This Scope

The PV loop proved the domain-loop architecture: fixed candidates, fixed
experiments, fixed scorecard, conservative promotion, memory reuse. Battery
v1 applies the same pattern to a slower, richer energy-storage domain at the
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

## Candidate Families

- `reduced_resistance` — Lower R0/R1 (better contacts/electrolyte)
- `improved_capacity` — Higher capacity_ah (thicker electrodes/better active material)
- `reduced_fade` — Lower fade_rate (better SEI stability)
- `improved_efficiency` — Higher coulombic_eff (fewer side reactions)
- `combined_moderate` — Modest multi-parameter co-optimization
- `bounded_aggressive` — Near-limit parameters for fail-gate testing

## Hard Fail Gates

- Capacity retention < 50% after 50 cycles
- Coulombic efficiency < 90%
- Internal resistance > 200 mOhm (for a typical ~3Ah cell)
- Negative capacity or efficiency
- Physically contradictory parameter combinations
- Simulation numerical instability

## Memory Pattern

Same as PV:
- `IdeaMemoryEntry` — what family, why proposed, outcome, lesson
- `ExperimentMemoryEntry` — which template, informative metrics, weakness exposed
- Families with promotions get higher weight; consistent hard-fails get down-ranked
