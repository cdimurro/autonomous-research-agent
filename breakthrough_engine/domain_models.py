"""Domain-specific optimization loop contracts.

Minimal reusable models for narrow-domain scientific optimization loops.
First domain: PV I-V characterization. Future: battery, DC-DC.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .models import new_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Domain specification
# ---------------------------------------------------------------------------

class MetricSpec(BaseModel):
    """Definition of a single measurable metric within a domain."""
    name: str
    unit: str
    description: str = ""
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None
    higher_is_better: bool = True
    is_primary: bool = False


class DomainSpec(BaseModel):
    """Defines a narrow scientific domain for optimization loops."""
    id: str = Field(default_factory=new_id)
    name: str  # e.g. "pv_iv"
    display_name: str  # e.g. "PV I-V Characterization"
    description: str = ""
    metrics: list[MetricSpec] = Field(default_factory=list)
    banned_claims: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Experiment templates
# ---------------------------------------------------------------------------

class ExperimentTemplate(BaseModel):
    """A fixed, repeatable experiment configuration."""
    id: str = Field(default_factory=new_id)
    domain_name: str  # FK to DomainSpec.name
    name: str  # e.g. "stc_baseline", "irradiance_sweep"
    description: str = ""
    parameters: dict = Field(default_factory=dict)
    expected_duration_seconds: float = 60.0
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Candidates (domain-specific)
# ---------------------------------------------------------------------------

class CandidateStatus(str, enum.Enum):
    PROPOSED = "proposed"
    RUNNING = "running"
    EVALUATED = "evaluated"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    HARD_FAIL = "hard_fail"


class CandidateSpec(BaseModel):
    """A candidate hypothesis or design variation within a domain."""
    id: str = Field(default_factory=new_id)
    domain_name: str
    run_id: str = ""
    title: str
    description: str = ""
    parameters: dict = Field(default_factory=dict)
    rationale: str = ""
    source: str = "generated"  # "generated", "literature", "perturbation"
    parent_id: Optional[str] = None  # if derived from another candidate
    status: CandidateStatus = CandidateStatus.PROPOSED
    rejection_reason: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Experiment results
# ---------------------------------------------------------------------------

class ExperimentRunResult(BaseModel):
    """Result of running an experiment template on a candidate."""
    id: str = Field(default_factory=new_id)
    candidate_id: str
    template_id: str
    domain_name: str
    metrics: dict = Field(default_factory=dict)  # metric_name -> value
    raw_data: dict = Field(default_factory=dict)  # full I-V curve, sweeps, etc.
    duration_seconds: float = 0.0
    success: bool = True
    error_message: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Evaluation and promotion
# ---------------------------------------------------------------------------

class EvaluationResult(BaseModel):
    """Scored evaluation of a candidate across all experiments."""
    id: str = Field(default_factory=new_id)
    candidate_id: str
    domain_name: str
    score_components: dict = Field(default_factory=dict)  # component_name -> score
    final_score: float = 0.0
    hard_fail: bool = False
    hard_fail_reasons: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class PromotionDecision(str, enum.Enum):
    PROMOTED = "promoted"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class PromotionRecord(BaseModel):
    """Record of a promote/reject decision for a candidate."""
    id: str = Field(default_factory=new_id)
    candidate_id: str
    domain_name: str
    decision: PromotionDecision
    evaluation_id: str = ""
    reason: str = ""
    baseline_score: Optional[float] = None
    candidate_score: Optional[float] = None
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Memory entries
# ---------------------------------------------------------------------------

class IdeaMemoryEntry(BaseModel):
    """What candidate family was tried, why, and what was learned."""
    id: str = Field(default_factory=new_id)
    domain_name: str
    candidate_id: str
    candidate_title: str
    candidate_family: str = ""  # grouping for related candidates
    rationale: str = ""  # why it was proposed
    outcome: str = ""  # promoted / rejected
    lesson: str = ""  # what was learned
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class ExperimentMemoryEntry(BaseModel):
    """What experiment data was informative and why."""
    id: str = Field(default_factory=new_id)
    domain_name: str
    candidate_id: str
    template_name: str
    informative_metrics: list[str] = Field(default_factory=list)
    weakness_exposed: str = ""  # what sweep/condition revealed weakness
    stability_notes: str = ""
    runtime_seconds: float = 0.0
    reproducibility_score: float = 1.0  # 0-1, how reproducible the result was
    created_at: datetime = Field(default_factory=_utcnow)
