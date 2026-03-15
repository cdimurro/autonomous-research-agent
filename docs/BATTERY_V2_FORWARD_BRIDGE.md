# Battery v2 — Forward Bridge

**Status:** Design-only. Not implemented in this batch. Intentionally deferred.

## What Battery v2 Could Include

The current battery benchmark (v2) is a hardened ECM-based loop with
fast-charge and degradation awareness. The next stage of battery work
could deepen the domain in several directions:

### 1. Cathode-Focused Candidate Generation

Generate candidates that vary cathode chemistry parameters (Ni:Mn:Co ratio,
grain size, coating thickness) rather than only circuit-model parameters.
This would require a mapping from chemistry to ECM parameters, either via
lookup tables from published data or via a lightweight surrogate model.

**Why deferred:** Requires validated chemistry-to-ECM mappings. Current
ECM is sufficient for benchmark discipline.

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

### 4. PyBaMM Integration (Conditional)

If Python 3.14 compatibility is resolved, PyBaMM could provide:
- DFN (Doyle-Fuller-Newman) electrochemical model
- Validated parameterization for common cell chemistries
- More physically meaningful fast-charge and degradation behavior

**Why deferred:** Python 3.14 compatibility is a blocker. Do not force
this dependency.

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
