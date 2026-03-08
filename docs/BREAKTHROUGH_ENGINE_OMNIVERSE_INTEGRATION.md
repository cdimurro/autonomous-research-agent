# Breakthrough Engine - Omniverse Integration Guide

## Current State (Phase 2)

The Omniverse integration provides a **dry-run bundle adapter** that creates structured execution packages for NVIDIA Omniverse Kit / Isaac Sim. No live Omniverse connection is required.

## Architecture

```
SimulatorAdapter (ABC)
  |-- MockSimulatorAdapter    (deterministic, for tests/demos)
  |-- OmniverseSimulatorAdapter
       |-- dry_run=True   -> builds execution bundles (Phase 2)
       |-- dry_run=False  -> live Omniverse connection (future)
```

## Bundle Structure

When a candidate passes all harness gates, the Omniverse adapter creates:

```
runtime/omniverse_bundles/<spec_id>/
  spec.json       # Full SimulationSpec with parameters
  config.json     # Omniverse-specific solver config
  README.md       # Human-readable execution instructions
  results/        # Empty directory for result files
```

## Building a Bundle

### Via CLI
```bash
python -m breakthrough_engine omniverse build-bundle --candidate-id <ID>
```

### Via API
```bash
curl -X POST localhost:8099/api/breakthrough/omniverse/build-bundle \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "abc123"}'
```

### Programmatic
```python
from breakthrough_engine.simulator import OmniverseSimulatorAdapter
from breakthrough_engine.models import SimulationSpec

adapter = OmniverseSimulatorAdapter(dry_run=True)
spec = SimulationSpec(
    candidate_id="abc123",
    objective="Validate solar cell efficiency prediction",
    parameters={"temperature": 300, "pressure": 1.0},
)
bundle_path = adapter.build_bundle(spec)
```

## Result Contract

After running the simulation externally, place a `result.json` in the bundle's `results/` directory:

```json
{
  "candidate_id": "abc123",
  "spec_id": "spec_001",
  "status": "completed",
  "key_metrics": {
    "success": true,
    "confidence": 0.85,
    "effect_size": 0.42
  },
  "pass_fail_summary": "Simulation converged with positive results",
  "completed_at": "2024-01-15T12:00:00Z"
}
```

Required fields: `candidate_id`, `spec_id`, `status`, `key_metrics`

Status values: `completed`, `failed`, `timeout`

## Ingesting Results

### Via CLI
```bash
python -m breakthrough_engine omniverse ingest-result path/to/result.json
```

### Programmatic
```python
result = OmniverseSimulatorAdapter.ingest_result("path/to/result.json")
# result is a SimulationResult object, saved to DB
```

## What Remains for Full Live Integration

1. **Omniverse Kit SDK connection** — connect to a running Omniverse instance via its API
2. **USD scene generation** — translate SimulationSpec parameters into USD scene descriptions
3. **PhysX solver configuration** — map hypothesis parameters to physics solver settings
4. **Real-time monitoring** — poll simulation progress and handle timeouts
5. **Automated result extraction** — parse simulation state into result metrics
6. **GPU resource management** — handle multi-simulation scheduling on limited GPU resources

## Run Modes

| Mode | Behavior |
|------|----------|
| `omniverse_dry_run` | Creates bundles, returns dry-run results |
| `omniverse_stub` | Legacy stub, uses `get_simulator("omniverse")` |
| Future: `omniverse_live` | Connects to running Omniverse instance |
