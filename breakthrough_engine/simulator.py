"""Simulator adapter layer.

Provides an abstract interface and concrete implementations:
- MockSimulatorAdapter: deterministic results for tests and demos
- OmniverseSimulatorAdapter: dry-run bundle builder for Omniverse integration
"""

from __future__ import annotations

import abc
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import SimulationResult, SimulationSpec, SimulationStatus, new_id

logger = logging.getLogger(__name__)


class SimulatorAdapter(abc.ABC):
    """Abstract base for simulator backends."""

    @abc.abstractmethod
    def run(self, spec: SimulationSpec) -> SimulationResult:
        """Execute a simulation and return the result."""

    @abc.abstractmethod
    def estimate_runtime(self, spec: SimulationSpec) -> float:
        """Estimate runtime in minutes for a given spec."""


class MockSimulatorAdapter(SimulatorAdapter):
    """Deterministic mock simulator for tests and local demos.

    Produces consistent, realistic-enough outputs based on spec content hashing.
    Same spec always produces the same result.
    """

    def run(self, spec: SimulationSpec) -> SimulationResult:
        # Deterministic seed from spec content
        content = json.dumps(
            {"candidate_id": spec.candidate_id, "params": spec.parameters,
             "objective": spec.objective},
            sort_keys=True,
        )
        hash_val = int(hashlib.sha256(content.encode()).hexdigest()[:8], 16)
        success_probability = (hash_val % 100) / 100.0

        # Simulate based on hash-derived "probability"
        success = success_probability > 0.3  # 70% of specs will succeed

        if success:
            metrics = {
                "success": True,
                "confidence": round(0.6 + (hash_val % 40) / 100.0, 3),
                "effect_size": round(0.1 + (hash_val % 90) / 100.0, 3),
                "iterations_completed": 100 + (hash_val % 900),
                "convergence_achieved": True,
            }
            summary = "Simulation completed successfully. Key metrics within expected bounds."
        else:
            metrics = {
                "success": False,
                "confidence": round((hash_val % 30) / 100.0, 3),
                "effect_size": round((hash_val % 10) / 100.0, 3),
                "iterations_completed": 10 + (hash_val % 90),
                "convergence_achieved": False,
            }
            summary = "Simulation did not converge within allocated iterations."

        return SimulationResult(
            id=new_id(),
            candidate_id=spec.candidate_id,
            spec_id=spec.id,
            status=SimulationStatus.COMPLETED,
            key_metrics=metrics,
            pass_fail_summary=summary,
            notes=f"Mock simulation (deterministic, hash={hash_val})",
            completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    def estimate_runtime(self, spec: SimulationSpec) -> float:
        return spec.estimated_runtime_minutes


# ---------------------------------------------------------------------------
# Omniverse Dry-Run / Bundle Adapter
# ---------------------------------------------------------------------------

# Expected result contract schema
OMNIVERSE_RESULT_SCHEMA = {
    "required_fields": ["candidate_id", "spec_id", "status", "key_metrics"],
    "status_values": ["completed", "failed", "timeout"],
    "key_metrics_required": ["success", "confidence"],
    "version": "1.0",
}


class OmniverseSimulatorAdapter(SimulatorAdapter):
    """Omniverse integration adapter with dry-run bundle support.

    In dry-run mode (default), creates a structured execution bundle
    containing all inputs needed for an external Omniverse runner.
    The bundle can be submitted to Omniverse Kit / Isaac Sim later.

    In live mode (future), would connect to a running Omniverse instance.
    """

    def __init__(
        self,
        bundle_dir: Optional[str] = None,
        dry_run: bool = True,
        omniverse_host: Optional[str] = None,
    ):
        self.dry_run = dry_run
        self.omniverse_host = omniverse_host
        root = bundle_dir or os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"),
            "omniverse_bundles",
        )
        self.bundle_dir = Path(root)
        self.bundle_dir.mkdir(parents=True, exist_ok=True)

    def run(self, spec: SimulationSpec) -> SimulationResult:
        if self.dry_run:
            return self._run_dry(spec)
        else:
            raise NotImplementedError(
                "Live Omniverse execution is not yet implemented. "
                "Use dry_run=True to generate execution bundles."
            )

    def _run_dry(self, spec: SimulationSpec) -> SimulationResult:
        """Create an execution bundle and return a dry-run result."""
        bundle_path = self.build_bundle(spec)
        logger.info("Omniverse dry-run bundle created: %s", bundle_path)

        return SimulationResult(
            id=new_id(),
            candidate_id=spec.candidate_id,
            spec_id=spec.id,
            status=SimulationStatus.COMPLETED,
            key_metrics={
                "success": True,
                "confidence": 0.5,
                "dry_run": True,
                "bundle_path": str(bundle_path),
            },
            pass_fail_summary="Dry-run: execution bundle created successfully. Submit to Omniverse for real results.",
            raw_artifact_path=str(bundle_path),
            notes="Omniverse dry-run mode — bundle ready for external execution",
            completed_at=datetime.now(timezone.utc),
        )

    def build_bundle(self, spec: SimulationSpec) -> Path:
        """Build a structured execution bundle for Omniverse.

        Bundle structure:
          bundles/<spec_id>/
            spec.json        — full SimulationSpec
            config.json       — Omniverse-specific config
            README.md         — human-readable instructions
            results/          — empty dir for result ingestion
        """
        bundle_id = spec.id or new_id()
        bundle_path = self.bundle_dir / bundle_id
        bundle_path.mkdir(parents=True, exist_ok=True)
        (bundle_path / "results").mkdir(exist_ok=True)

        # Write spec
        spec_data = {
            "id": spec.id,
            "candidate_id": spec.candidate_id,
            "simulator": spec.simulator,
            "objective": spec.objective,
            "parameters": spec.parameters,
            "constraints": spec.constraints,
            "estimated_runtime_minutes": spec.estimated_runtime_minutes,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(bundle_path / "spec.json", "w") as f:
            json.dump(spec_data, f, indent=2)

        # Write Omniverse config
        config = {
            "omniverse_version": "2024.1",
            "solver": "PhysX",
            "scene_type": "scientific_simulation",
            "max_iterations": spec.parameters.get("max_iterations", 1000),
            "time_step": spec.parameters.get("time_step", 0.001),
            "convergence_threshold": spec.parameters.get("convergence_threshold", 1e-6),
            "gpu_required": True,
            "result_contract": OMNIVERSE_RESULT_SCHEMA,
        }
        with open(bundle_path / "config.json", "w") as f:
            json.dump(config, f, indent=2)

        # Write README
        readme = f"""# Omniverse Simulation Bundle

**Spec ID:** {spec.id}
**Candidate ID:** {spec.candidate_id}
**Objective:** {spec.objective}

## How to Execute

1. Start Omniverse Kit or Isaac Sim
2. Load this bundle's spec.json
3. Configure the simulation using config.json
4. Run the simulation
5. Save results to the `results/` directory as `result.json`

## Expected Result Format

The result.json must contain:
- `candidate_id`: string (must match spec)
- `spec_id`: string (must match spec)
- `status`: "completed" | "failed" | "timeout"
- `key_metrics`: object with at least `success` (bool) and `confidence` (float)
- `pass_fail_summary`: string
- `completed_at`: ISO datetime string

## Ingestion

After execution, ingest results via:
```
python -m breakthrough_engine omniverse ingest-result {bundle_path}/results/result.json
```
"""
        with open(bundle_path / "README.md", "w") as f:
            f.write(readme)

        return bundle_path

    def estimate_runtime(self, spec: SimulationSpec) -> float:
        return spec.estimated_runtime_minutes * 3.0

    @staticmethod
    def validate_config(spec: SimulationSpec) -> list[str]:
        """Validate that a spec has required configuration for Omniverse."""
        errors = []
        if not spec.candidate_id:
            errors.append("candidate_id is required")
        if not spec.objective:
            errors.append("objective is required")
        if spec.estimated_runtime_minutes <= 0:
            errors.append("estimated_runtime_minutes must be positive")
        return errors

    @staticmethod
    def ingest_result(result_path: str) -> SimulationResult:
        """Read back a result JSON from a known path and map to SimulationResult."""
        path = Path(result_path)
        if not path.exists():
            raise FileNotFoundError(f"Result file not found: {result_path}")

        with open(path) as f:
            data = json.load(f)

        # Validate required fields
        for req_field in OMNIVERSE_RESULT_SCHEMA["required_fields"]:
            if req_field not in data:
                raise ValueError(f"Missing required field in result: {req_field}")

        status_str = data.get("status", "failed")
        status_map = {
            "completed": SimulationStatus.COMPLETED,
            "failed": SimulationStatus.FAILED,
            "timeout": SimulationStatus.FAILED,
        }
        status = status_map.get(status_str, SimulationStatus.FAILED)

        completed_at = None
        if data.get("completed_at"):
            try:
                completed_at = datetime.fromisoformat(data["completed_at"])
            except (ValueError, TypeError):
                completed_at = datetime.now(timezone.utc)

        return SimulationResult(
            id=new_id(),
            candidate_id=data["candidate_id"],
            spec_id=data.get("spec_id", ""),
            status=status,
            key_metrics=data.get("key_metrics", {}),
            pass_fail_summary=data.get("pass_fail_summary", ""),
            raw_artifact_path=str(path),
            notes=data.get("notes", f"Ingested from {result_path}"),
            completed_at=completed_at,
        )


def get_simulator(name: str, **kwargs) -> SimulatorAdapter:
    """Factory for simulator adapters."""
    if name == "mock":
        return MockSimulatorAdapter()
    elif name in ("omniverse", "omniverse_dry_run"):
        return OmniverseSimulatorAdapter(dry_run=True, **kwargs)
    elif name == "omniverse_live":
        return OmniverseSimulatorAdapter(dry_run=False, **kwargs)
    else:
        raise ValueError(f"Unknown simulator: {name}. Available: mock, omniverse, omniverse_dry_run")
