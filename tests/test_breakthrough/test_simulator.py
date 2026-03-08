"""Tests for simulator adapters."""

import json
import os
import tempfile

import pytest

from breakthrough_engine.models import SimulationSpec, SimulationStatus
from breakthrough_engine.simulator import (
    MockSimulatorAdapter,
    OmniverseSimulatorAdapter,
    get_simulator,
)


class TestMockSimulator:
    def test_produces_result(self):
        sim = MockSimulatorAdapter()
        spec = SimulationSpec(
            candidate_id="c1", simulator="mock",
            objective="Test", parameters={"x": 1},
            estimated_runtime_minutes=5.0,
        )
        result = sim.run(spec)
        assert result.status == SimulationStatus.COMPLETED
        assert result.candidate_id == "c1"
        assert "success" in result.key_metrics

    def test_deterministic(self):
        sim = MockSimulatorAdapter()
        spec = SimulationSpec(
            candidate_id="c1", simulator="mock",
            objective="Test", parameters={"x": 1},
        )
        r1 = sim.run(spec)
        r2 = sim.run(spec)
        assert r1.key_metrics == r2.key_metrics
        assert r1.pass_fail_summary == r2.pass_fail_summary

    def test_different_specs_different_results(self):
        sim = MockSimulatorAdapter()
        s1 = SimulationSpec(candidate_id="c1", objective="A", parameters={"x": 1})
        s2 = SimulationSpec(candidate_id="c2", objective="B", parameters={"y": 99})
        r1 = sim.run(s1)
        r2 = sim.run(s2)
        # Results should differ (different hashes)
        assert r1.key_metrics != r2.key_metrics or r1.candidate_id != r2.candidate_id

    def test_estimate_runtime(self):
        sim = MockSimulatorAdapter()
        spec = SimulationSpec(candidate_id="c1", estimated_runtime_minutes=10.0)
        assert sim.estimate_runtime(spec) == 10.0


class TestOmniverseDryRun:
    def test_dry_run_produces_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sim = OmniverseSimulatorAdapter(bundle_dir=tmpdir, dry_run=True)
            spec = SimulationSpec(
                candidate_id="c1", simulator="omniverse",
                objective="Test hypothesis",
            )
            result = sim.run(spec)
            assert result.status == SimulationStatus.COMPLETED
            assert result.candidate_id == "c1"
            assert result.key_metrics.get("dry_run") is True
            assert result.raw_artifact_path  # bundle path set

    def test_build_bundle_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sim = OmniverseSimulatorAdapter(bundle_dir=tmpdir, dry_run=True)
            spec = SimulationSpec(
                id="test_spec_001",
                candidate_id="c1",
                simulator="omniverse",
                objective="Validate solar cell efficiency",
                parameters={"temperature": 300, "pressure": 1.0},
            )
            bundle_path = sim.build_bundle(spec)
            assert (bundle_path / "spec.json").exists()
            assert (bundle_path / "config.json").exists()
            assert (bundle_path / "README.md").exists()
            assert (bundle_path / "results").is_dir()

            # Verify spec.json content
            with open(bundle_path / "spec.json") as f:
                data = json.load(f)
            assert data["candidate_id"] == "c1"
            assert data["objective"] == "Validate solar cell efficiency"

    def test_live_mode_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sim = OmniverseSimulatorAdapter(bundle_dir=tmpdir, dry_run=False)
            spec = SimulationSpec(candidate_id="c1")
            with pytest.raises(NotImplementedError):
                sim.run(spec)

    def test_validate_config(self):
        spec = SimulationSpec(candidate_id="c1", objective="Test", estimated_runtime_minutes=5.0)
        errors = OmniverseSimulatorAdapter.validate_config(spec)
        assert len(errors) == 0

    def test_validate_config_errors(self):
        spec = SimulationSpec(candidate_id="", objective="", estimated_runtime_minutes=0)
        errors = OmniverseSimulatorAdapter.validate_config(spec)
        assert len(errors) >= 2

    def test_ingest_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result_data = {
                "candidate_id": "c1",
                "spec_id": "s1",
                "status": "completed",
                "key_metrics": {"success": True, "confidence": 0.85},
                "pass_fail_summary": "Simulation converged",
                "completed_at": "2024-01-15T12:00:00",
            }
            result_path = os.path.join(tmpdir, "result.json")
            with open(result_path, "w") as f:
                json.dump(result_data, f)

            result = OmniverseSimulatorAdapter.ingest_result(result_path)
            assert result.candidate_id == "c1"
            assert result.status == SimulationStatus.COMPLETED
            assert result.key_metrics["confidence"] == 0.85

    def test_ingest_result_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result_path = os.path.join(tmpdir, "bad_result.json")
            with open(result_path, "w") as f:
                json.dump({"status": "completed"}, f)

            with pytest.raises(ValueError, match="Missing required field"):
                OmniverseSimulatorAdapter.ingest_result(result_path)

    def test_ingest_result_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            OmniverseSimulatorAdapter.ingest_result("/nonexistent/result.json")

    def test_estimate_runtime(self):
        sim = OmniverseSimulatorAdapter(dry_run=True)
        spec = SimulationSpec(candidate_id="c1", estimated_runtime_minutes=10.0)
        assert sim.estimate_runtime(spec) == 30.0  # 3x multiplier


class TestGetSimulator:
    def test_get_mock(self):
        sim = get_simulator("mock")
        assert isinstance(sim, MockSimulatorAdapter)

    def test_get_omniverse(self):
        sim = get_simulator("omniverse")
        assert isinstance(sim, OmniverseSimulatorAdapter)

    def test_get_omniverse_dry_run(self):
        sim = get_simulator("omniverse_dry_run")
        assert isinstance(sim, OmniverseSimulatorAdapter)
        assert sim.dry_run is True

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            get_simulator("quantum_computer")
