"""Tests for config loader."""

import os
import tempfile

import pytest
import yaml

from breakthrough_engine.config_loader import (
    list_programs,
    load_program,
    validate_program,
)
from breakthrough_engine.models import ResearchProgram, RunMode


@pytest.fixture
def config_dir():
    with tempfile.TemporaryDirectory() as d:
        # Write a test config
        config = {
            "name": "test_prog",
            "domain": "test-domain",
            "goal": "Test goal",
            "candidate_budget": 5,
            "simulation_budget": 2,
            "scoring_weights": {
                "novelty": 0.20,
                "plausibility": 0.20,
                "impact": 0.20,
                "evidence_strength": 0.20,
                "simulation_readiness": 0.10,
                "inverse_validation_cost": 0.10,
            },
            "publication_threshold": 0.60,
            "novelty_threshold": 0.3,
            "evidence_minimum": 2,
            "allowed_simulators": ["mock"],
            "mode": "demo_local",
        }
        with open(os.path.join(d, "test_prog.yaml"), "w") as f:
            yaml.dump(config, f)
        yield d


def test_load_program(config_dir):
    prog = load_program("test_prog", config_dir=config_dir)
    assert prog.name == "test_prog"
    assert prog.domain == "test-domain"
    assert prog.candidate_budget == 5
    assert prog.mode == RunMode.DEMO_LOCAL


def test_load_program_not_found(config_dir):
    with pytest.raises(FileNotFoundError):
        load_program("nonexistent", config_dir=config_dir)


def test_list_programs(config_dir):
    programs = list_programs(config_dir=config_dir)
    assert "test_prog" in programs


def test_validate_program_valid():
    prog = ResearchProgram(name="test", domain="d")
    errors = validate_program(prog)
    assert errors == []


def test_validate_program_missing_name():
    prog = ResearchProgram(name="", domain="d")
    errors = validate_program(prog)
    assert any("name" in e.lower() for e in errors)


def test_validate_program_bad_threshold():
    prog = ResearchProgram(name="test", domain="d", publication_threshold=1.5)
    errors = validate_program(prog)
    assert any("threshold" in e.lower() for e in errors)


def test_validate_program_bad_weights():
    prog = ResearchProgram(
        name="test", domain="d",
        scoring_weights={"novelty": 0.5, "plausibility": 0.5, "impact": 0.5,
                         "evidence_strength": 0.2, "simulation_readiness": 0.1,
                         "inverse_validation_cost": 0.1},
    )
    errors = validate_program(prog)
    assert any("weights" in e.lower() for e in errors)


def test_load_real_general_fast_loop():
    """Test loading the actual shipped config."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_dir = os.path.join(repo_root, "config", "research_programs")
    if os.path.exists(os.path.join(config_dir, "general_fast_loop.yaml")):
        prog = load_program("general_fast_loop", config_dir=config_dir)
        assert prog.name == "general_fast_loop"
        errors = validate_program(prog)
        assert errors == []
