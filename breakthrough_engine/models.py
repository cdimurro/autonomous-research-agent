"""Domain models for the Breakthrough Engine.

All core entities, lifecycle enums, and typed schemas.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime (no tzinfo).

    Replaces deprecated datetime.utcnow() without changing behavior.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Lifecycle enums
# ---------------------------------------------------------------------------

class CandidateStatus(str, enum.Enum):
    GENERATED = "generated"
    DEDUP_REJECTED = "dedup_rejected"
    HYPOTHESIS_FAILED = "hypothesis_failed"
    EVIDENCE_FAILED = "evidence_failed"
    NOVELTY_FAILED = "novelty_failed"
    SIMULATION_FAILED = "simulation_failed"
    PUBLICATION_FAILED = "publication_failed"
    FINALIST = "finalist"
    DRAFT_PENDING_REVIEW = "draft_pending_review"
    PUBLISHED = "published"


class RunStatus(str, enum.Enum):
    STARTED = "started"
    COMPLETED = "completed"
    COMPLETED_NO_PUBLICATION = "completed_no_publication"
    FAILED = "failed"


class RunMode(str, enum.Enum):
    DETERMINISTIC_TEST = "deterministic_test"
    DEMO_LOCAL = "demo_local"
    PRODUCTION_LOCAL = "production_local"
    PRODUCTION_REVIEW = "production_review"
    PRODUCTION_SHADOW = "production_shadow"
    OMNIVERSE_STUB = "omniverse_stub"
    OMNIVERSE_DRY_RUN = "omniverse_dry_run"


class SimulationStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    id: str = Field(default_factory=new_id)
    source_type: str  # "paper", "finding", "fixture"
    source_id: str
    title: str
    quote: str
    citation: str
    relevance_score: float = 0.5


class EvidencePack(BaseModel):
    id: str = Field(default_factory=new_id)
    candidate_id: str
    items: list[EvidenceItem] = Field(default_factory=list)
    source_diversity_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------

class CandidateHypothesis(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str = ""
    title: str
    domain: str
    statement: str
    mechanism: str
    expected_outcome: str
    testability_window_hours: float = 24.0
    novelty_notes: str = ""
    assumptions: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    status: CandidateStatus = CandidateStatus.GENERATED
    rejection_reason: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class SimulationSpec(BaseModel):
    id: str = Field(default_factory=new_id)
    candidate_id: str
    simulator: str = "mock"
    objective: str = ""
    parameters: dict = Field(default_factory=dict)
    constraints: dict = Field(default_factory=dict)
    estimated_runtime_minutes: float = 5.0


class SimulationResult(BaseModel):
    id: str = Field(default_factory=new_id)
    candidate_id: str
    spec_id: str = ""
    status: SimulationStatus = SimulationStatus.PENDING
    key_metrics: dict = Field(default_factory=dict)
    pass_fail_summary: str = ""
    raw_artifact_path: str = ""
    notes: str = ""
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

class HarnessDecision(BaseModel):
    harness_name: str
    candidate_id: str
    passed: bool
    failed_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    score_contribution: float = 0.0
    explanation: str = ""


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class CandidateScore(BaseModel):
    candidate_id: str
    novelty_score: float = 0.0
    plausibility_score: float = 0.0
    impact_score: float = 0.0
    validation_cost_score: float = 0.0  # 0=cheap, 1=expensive
    evidence_strength_score: float = 0.0
    simulation_readiness_score: float = 0.0
    final_score: float = 0.0

    def compute_final(self, weights: Optional[dict] = None) -> float:
        w = weights or {
            "novelty": 0.20,
            "plausibility": 0.20,
            "impact": 0.20,
            "evidence_strength": 0.20,
            "simulation_readiness": 0.10,
            "inverse_validation_cost": 0.10,
        }
        self.final_score = (
            self.novelty_score * w["novelty"]
            + self.plausibility_score * w["plausibility"]
            + self.impact_score * w["impact"]
            + self.evidence_strength_score * w["evidence_strength"]
            + self.simulation_readiness_score * w["simulation_readiness"]
            + (1.0 - self.validation_cost_score) * w["inverse_validation_cost"]
        )
        return self.final_score


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

class PublicationRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    publication_date: datetime = Field(default_factory=_utcnow)
    candidate_id: str
    candidate_title: str
    abstract: str = ""
    hypothesis: str
    score_breakdown: dict = Field(default_factory=dict)
    evidence_summary: str = ""
    simulation_summary: str = ""
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    replication_priority: str = "medium"
    status_label: str = "validated_breakthrough_candidate"


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

class RunRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    program_name: str
    mode: RunMode = RunMode.DEMO_LOCAL
    status: RunStatus = RunStatus.STARTED
    candidates_generated: int = 0
    candidates_rejected: int = 0
    publication_id: Optional[str] = None
    error_message: str = ""
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Research Program (loaded from YAML)
# ---------------------------------------------------------------------------

class ResearchProgram(BaseModel):
    name: str
    domain: str
    goal: str = ""
    candidate_budget: int = 10
    simulation_budget: int = 3
    scoring_weights: dict = Field(default_factory=lambda: {
        "novelty": 0.20,
        "plausibility": 0.20,
        "impact": 0.20,
        "evidence_strength": 0.20,
        "simulation_readiness": 0.10,
        "inverse_validation_cost": 0.10,
    })
    novelty_threshold: float = 0.3
    evidence_minimum: int = 2
    allowed_simulators: list[str] = Field(default_factory=lambda: ["mock"])
    publication_threshold: float = 0.60
    banned_claims: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    runtime_budget_minutes: int = 60
    validation_policy: str = "strict"
    mode: RunMode = RunMode.DEMO_LOCAL


# ---------------------------------------------------------------------------
# Phase 3: Novelty
# ---------------------------------------------------------------------------

class NoveltyDecision(str, enum.Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class PriorArtHit(BaseModel):
    source: str  # "local_candidate", "retrieved_paper", "publication"
    source_id: str
    title: str
    similarity: float
    overlap_type: str  # "exact_title", "statement_overlap", "mechanism_overlap", "keyword"


class NoveltyResult(BaseModel):
    id: str = Field(default_factory=new_id)
    candidate_id: str
    novelty_score: float = 0.0
    duplicate_risk_score: float = 0.0
    prior_art_hits: list[PriorArtHit] = Field(default_factory=list)
    overlap_reasons: list[str] = Field(default_factory=list)
    decision: NoveltyDecision = NoveltyDecision.PASS
    warnings: list[str] = Field(default_factory=list)
    explanation: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Phase 3: Publication Drafts + Review
# ---------------------------------------------------------------------------

class DraftStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublicationDraft(BaseModel):
    id: str = Field(default_factory=new_id)
    run_id: str
    candidate_id: str
    candidate_title: str
    abstract: str = ""
    hypothesis: str
    score_breakdown: dict = Field(default_factory=dict)
    evidence_summary: str = ""
    simulation_summary: str = ""
    novelty_summary: str = ""
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    replication_priority: str = "medium"
    status: DraftStatus = DraftStatus.PENDING_REVIEW
    created_at: datetime = Field(default_factory=_utcnow)
    reviewed_at: Optional[datetime] = None


class ReviewAction(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ReviewEvent(BaseModel):
    id: str = Field(default_factory=new_id)
    draft_id: str
    run_id: str
    candidate_id: str
    action: ReviewAction
    reviewer: str = "operator"
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Phase 3: Run Metrics
# ---------------------------------------------------------------------------

class RunMetrics(BaseModel):
    run_id: str
    stage_durations: dict = Field(default_factory=dict)  # stage_name -> seconds
    candidates_by_status: dict = Field(default_factory=dict)  # status -> count
    evidence_count: int = 0
    novelty_fail_count: int = 0
    novelty_warn_count: int = 0
    simulation_pass_count: int = 0
    simulation_fail_count: int = 0
    draft_created: bool = False
    publication_created: bool = False
    total_duration_seconds: float = 0.0
    created_at: datetime = Field(default_factory=_utcnow)
