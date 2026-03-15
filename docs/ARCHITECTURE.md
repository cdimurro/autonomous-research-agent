# Breakthrough Engine — Architecture and Direction

**Last Updated:** 2026-03-14

## What the Breakthrough Engine Is

The Breakthrough Engine is a repeatable scientific optimization loop engine. It:

1. Takes a narrow scientific domain (e.g., PV I-V characterization)
2. Proposes candidate hypotheses or design variations
3. Runs fixed, comparable experiments against each candidate
4. Computes explicit, inspectable metrics
5. Scores, promotes, or rejects candidates through deterministic gates
6. Persists all lessons (idea memory, experiment memory) for future runs
7. Repeats — each loop building on accumulated knowledge

The system is designed to be domain-agnostic at the contract layer but domain-specific at the pack layer.

## Current Production Core

### Retrieval
- **Production default:** `HybridKGEvidenceSource` (graph-native, promoted Phase 10K)
- Combines trusted database findings + knowledge graph segments/entities/relations
- Source-aware pool construction with diversity guarantees

### Scoring
- 7-dimension weighted formula (novelty, plausibility, impact, evidence strength, simulation readiness, validation cost)
- Source-type-aware trust weighting for evidence strength
- Policy-configurable weights

### Campaign Ladder
- 5-stage quality-first pipeline: broad exploration → shortlist → falsification → review → champion selection
- Bounded execution (wall-clock or trial count)
- Campaign receipts and artifact persistence

### Policy System
- Champion/challenger lifecycle with A/B trials
- Manual promotion with rollback guardrails
- Current champion: `evidence_diversity_v1`

## Domain Rollout Plan

The engine is being extended with narrow, measurable domain-specific optimization loops. Each domain gets a "domain pack" containing:

- `DomainSpec` — what the domain is, what it measures
- `MetricSpec` — explicit metric definitions with units and bounds
- `ExperimentTemplate` — fixed, repeatable experiment configurations
- Candidate generation logic specific to the domain
- Scoring and hard-fail gates calibrated to the domain

### Rollout Order

| Priority | Domain | Status | Why |
|----------|--------|--------|-----|
| 1 | **PV I-V Characterization** | **Stable (benchmark)** | Clear metrics (Voc, Isc, FF, efficiency), cheap simulation via pvlib, strong clean-energy relevance |
| 2 | **Battery ECM + Cycle** | **Active** | Equivalent-circuit and cycle characterization — same loop pattern, energy-storage physics |
| 3 | DC-DC Converter Optimization | Planned | Power electronics — different candidate space, same loop pattern |

### What Is Intentionally Deferred

- **Atomistic materials discovery** — No cathode chemistry invention. Battery v1 operates at the equivalent-circuit / cycle-characterization level.
- **Pack-scale thermal twins** — No multi-cell thermal simulation. Single-cell characterization only.
- **Omniverse integration** — Deferred until higher-fidelity validation is justified.
- **Web UI / Project Zero integration** — The engine produces auditable artifacts (JSON, SQLite, Markdown) that a future UI can consume.
- **DC-DC domain** — Comes after battery loop is proven.
- **Paper-generation polish** — The publication system exists but domain loop output is scientific data, not papers.

## Contract Layer Architecture

The optimization loop is built on minimal reusable contracts:

```
DomainSpec          — "What domain is this?"
MetricSpec          — "What do we measure and how?"
ExperimentTemplate  — "What fixed experiment do we run?"
CandidateSpec       — "What is a candidate in this domain?"
ExperimentRunResult — "What happened when we ran the experiment?"
EvaluationResult    — "How did the candidate score?"
PromotionDecision   — "Promote or reject, and why?"
IdeaMemoryEntry     — "What did we try and what did we learn?"
ExperimentMemoryEntry — "What experiment data was informative?"
```

These contracts are Pydantic models, stored in SQLite, and designed to be auditable. They do not replace the existing broad-domain pipeline — they extend it with a domain-specific experiment layer.

## How Domain Loops Fit Into Existing Architecture

```
Existing Pipeline (preserved):
  Evidence → Generate → Gate → Score → Publish

Domain Loops (additive, per-domain):
  DomainSpec → CandidateGenerator → ExperimentRunner
    → MetricExtractor → Scorer → Promote/Reject
    → IdeaMemory + ExperimentMemory persistence

PV Loop (benchmark domain):
  pvlib single-diode model → STC + sweep experiments → Pmax/FF/efficiency scoring

Battery Loop (active domain):
  Thevenin ECM + capacity-fade model → charge/discharge + cycle aging + C-rate sweep
  → capacity retention / coulombic efficiency / resistance / fade scoring

Integration point:
  Research programs:  config/research_programs/{pv_iv,battery_ecm}.yaml
  Daily profiles:     config/daily_profiles/{pv_evaluation,battery_evaluation}.yaml
  CLI:                python -m breakthrough_engine {pv,battery} {run,benchmark,...}
```

Domain loops run as research programs alongside the existing clean-energy program. They do not replace or destabilize the current production path.

## Data Sources

### Production (no API key required)
- `pvlib` — PV modeling/simulation library (STC conditions, I-V curves, temperature/irradiance sweeps)
- Built-in PV parameter datasets (CEC module database via pvlib)
- `numpy` / `scipy` — Battery equivalent-circuit model (Thevenin ECM + capacity-fade simulation)
- Offline fixtures for testing

### Optional (API key, disabled by default)
- NREL NSRDB — Solar irradiance data (requires `NREL_API_KEY` env var)
- PVWatts — System performance estimation (requires `NREL_API_KEY` env var)

## Key Invariants

1. One publication/promotion per run (preserved)
2. Champion-only for production automation (preserved)
3. All tests offline-safe (preserved)
4. Existing graph-native retrieval path unchanged
5. Domain experiments are fixed and comparable across runs
6. All candidates scored against explicit physics-based metrics
7. Hard-fail gates reject unphysical parameter combinations
8. Each domain loop is self-contained: its own metrics, families, scoring, memory
