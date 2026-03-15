# Battery ECM Domain — Hardened Benchmark (v2)

**Status:** Flagship benchmark domain — fast-charge and degradation-aware proving ground

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
applies the same pattern to a richer energy-storage domain at the
equivalent-circuit level — the simplest model that produces interpretable,
measurable, and comparable outputs. Since v2, the benchmark is explicitly
aligned with fast-charge and degradation performance, making it a useful
staging ground for future cathode-focused work.

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

| Metric | Unit | Primary | Why It Matters |
|--------|------|---------|---------------|
| `discharge_capacity` | Ah | Yes | Primary output — how much energy the cell delivers |
| `coulombic_efficiency` | % | Yes | Charge/discharge ratio — indicates side reactions |
| `internal_resistance` | mOhm | Yes | Ohmic + polarization — indicates power capability |
| `capacity_retention` | % | Yes | After N cycles — indicates longevity |
| `fade_rate` | %/cycle | Yes | Capacity loss rate — indicates degradation speed |
| `fast_charge_retention` | % | Yes | Retention after 3C/30-cycle stress — fast-charge durability |
| `energy_efficiency` | % | No | Wh_out / Wh_in — round-trip efficiency |
| `rate_capability` | ratio | No | Capacity at high C-rate / capacity at low C-rate |
| `resistance_growth_pct` | % | No | Impedance increase under fast-charge stress |

## Fixed Experiment Templates

1. **baseline_cycle** — 1C charge/discharge at 25C, extract basic metrics
2. **cycle_aging** — 50-cycle aging at 1C, track capacity retention and fade
3. **crate_sweep** — C/3, C/2, 1C, 2C, 3C discharge sweep, extract rate capability
4. **pulse_resistance** — 10s discharge pulse at 50% SOC for resistance characterization
5. **thermal_sensitivity** — Baseline cycle at 10C, 25C, 40C, 55C
6. **fast_charge_stress** — 20-cycle aging at 2C, measuring fast-charge fade penalty
7. **thermal_stress_aging** — 20-cycle aging at 1C/45C, measuring thermal degradation
8. **repeated_fast_charge_stress** — 30-cycle aging at 3C, measuring sustained fast-charge degradation, capacity retention, and resistance growth

## Candidate Families

Each family has bounded perturbation ranges, physical rationale, documented
tradeoff risk, and realistic tradeoff penalties.

- `reduced_resistance` — Lower R0/R1 (better contacts/electrolyte). Risk: thinner separator; fast-charge fade.
- `improved_capacity` — Higher capacity_ah with small fade penalty (Si-graphite anode, high-Ni cathode). Risk: faster fade; rate capability loss.
- `reduced_fade` — Lower fade_rate with small R1 penalty (electrolyte additives, ALD coatings). Risk: higher impedance.
- `improved_efficiency` — Higher coulombic_eff (reduced parasitic reactions). Risk: thermal sensitivity.
- `combined_moderate` — Modest multi-lever co-optimization. Risk: interaction effects.
- `rate_optimized` — Optimized for fast-charge: lower R0/R1, modest capacity tradeoff. Risk: energy density loss; thermal management critical.
- `bounded_aggressive` — Near-best-in-class parameters. Risk: requires advanced manufacturing; fast-charge unverified.

Parameter ranges are grounded in published 18650/21700 datasheet values with 5
commercial cell references as anchors (Sony VTC6, Samsung 50E, Samsung 30Q,
LG MJ1, Molicel P42A).

## Cross-Parameter Plausibility

7 checks reject physically contradictory parameter combinations at generation time:
1. Low R0 + high fade (stable interfaces don't degrade fast)
2. High capacity + low CE (thermal safety)
3. Low R0 + high R1 (inconsistent transport properties)
4. High capacity + low R0 (thick electrodes increase path length)
5. High fade + high CE (rapid fade implies side reactions)
6. Standard physical plausibility (positive values, bounded ranges)
7. Low fade + high R0 (low degradation unlikely to survive fast-charge stress)

## Hard Fail Gates

- Capacity retention < 50% after 50 cycles
- Coulombic efficiency < 90%
- Internal resistance > 200 mOhm
- Worst-case stress retention < 80%
- Resistance growth > 20% under fast-charge stress
- Stress resilience score < 0.40 (promotion gate)
- Regime-specificity gate: extreme component imbalance (max > 0.85, min < 0.15)
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
| `stress_resilience` | 15% | Fast-charge + thermal stress retention + resistance growth penalty |
| `plausibility_penalty` | 15% | Metrics plausibility check |

Stress resilience now penalizes:
- Resistance growth > 5% under fast-charge stress
- Repeated fast-charge retention < 90% (3C/30-cycle)

## Promotion Policy

- Max 1 promoted candidate per run
- Optional 1 alternate with different family and near-threshold score
- Stress gate: stress_resilience >= 0.40
- Regime gate: no extreme component imbalance
- Rate-tradeoff collapse detection: resistance improvement without rate capability

## Memory Pattern

Two-phase memory-guided generation:
1. **IdeaMemory** — outcome-based: promoted families get higher weight, hard-fail
   families get down-ranked, all-rejected families get recovery tag
2. **ExperimentMemory** — weakness-based: stress fragility, fast-charge weakness,
   resistance growth weakness tracked separately; families with repeated battery-
   specific weakness get extra down-weighting

Battery-specific lessons extracted:
- Fast-charge degradation trend (good nominal fade but poor fast-charge durability)
- Resistance improvement without rate capability (tradeoff lesson)
- 3C durability and impedance growth

Proposal tags: `[memory-supported]`, `[exploratory]`, `[recovery]`,
`[retry-with-correction]`, `[stress-informed]`

## Benchmark Mode

Battery is the flagship benchmark domain. Run with:

```bash
python -m breakthrough_engine battery benchmark --seed 42
```

The benchmark report (v2) includes:
- Baseline metrics
- Best candidate with score, metrics, rationale, and caveats
- Stress profile (2C + 3C fast-charge + thermal)
- Degradation profile (fade ratios across stress scenarios)
- Per-candidate breakdown with rejection reasons
- Family summary (counts, scores, promotion rates)
- Held-out reference comparison (within envelope check)
- Stability indicators for regression detection

## Baseline Freeze

The pre-deepening benchmark is preserved as `runtime/battery_loop/battery_baseline_v1_frozen.json`.
This is the known-good reference for regression comparison.

## Known Limitations (Intentionally Deferred)

- 1RC model only (no 2RC or distributed elements)
- Empirical fade model (not physics-based SEI growth)
- No calendar aging (only cycle aging)
- No state-of-health estimation
- No pack-level effects (thermal management, cell balancing)
- No cathode chemistry variation (fixed NMC assumed)
- Resistance growth in ECM is modeled via capacity-fade proxy (not true
  impedance evolution); the `resistance_growth_pct` metric reflects this
  limitation
