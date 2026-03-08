"""Research program YAML configuration loader."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import ResearchProgram


def _config_dir() -> Path:
    repo_root = os.environ.get(
        "SCIRES_REPO_ROOT",
        str(Path(__file__).resolve().parent.parent),
    )
    return Path(repo_root) / "config" / "research_programs"


def load_program(name: str, config_dir: str | Path | None = None) -> ResearchProgram:
    """Load a research program from YAML by name (without extension)."""
    d = Path(config_dir) if config_dir else _config_dir()
    path = d / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Research program config not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    return ResearchProgram(**data)


def list_programs(config_dir: str | Path | None = None) -> list[str]:
    """Return names of all available research programs."""
    d = Path(config_dir) if config_dir else _config_dir()
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def validate_program(program: ResearchProgram) -> list[str]:
    """Return a list of validation errors (empty if valid)."""
    errors = []
    if not program.name:
        errors.append("Program name is required")
    if not program.domain:
        errors.append("Domain is required")
    if program.candidate_budget < 1:
        errors.append("candidate_budget must be >= 1")
    if program.simulation_budget < 0:
        errors.append("simulation_budget must be >= 0")
    if not (0.0 <= program.publication_threshold <= 1.0):
        errors.append("publication_threshold must be between 0.0 and 1.0")
    if not (0.0 <= program.novelty_threshold <= 1.0):
        errors.append("novelty_threshold must be between 0.0 and 1.0")
    weights = program.scoring_weights
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        errors.append(f"Scoring weights must sum to 1.0 (got {total:.3f})")
    return errors
