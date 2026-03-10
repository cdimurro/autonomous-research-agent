"""Reviewed baseline registry for the Breakthrough Engine Phase 8.

Manages two trusted baselines:
  - phase5_validated: Deterministic benchmark baseline (FakeCandidateGenerator)
  - phase7d_reviewed: Evaluated-grade batch baseline (real embeddings, real campaigns)

The two baselines serve different purposes:
  - phase5_validated: Long-term algorithmic regression testing (use for champion promotion)
  - phase7d_reviewed: Real-world reviewed quality anchoring (use for policy learning comparison)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

BASELINES_DIR = os.path.join(
    os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "baselines"
)

KNOWN_BASELINES = {
    "phase5_validated": "phase5_validated_benchmark.json",
    "phase7d_reviewed": "phase7d_reviewed_baseline.json",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class ReviewedBaseline:
    """A frozen trusted baseline reference."""
    baseline_id: str
    baseline_name: str
    baseline_type: str          # "deterministic_benchmark" | "reviewed_evaluation"
    frozen_at: str
    branch: str
    commit: str
    schema_version: str
    profile: str
    domain: str
    generation_model: str
    embedding_model: str
    champion_policy: str
    batch_id: str
    campaign_ids: list = field(default_factory=list)
    campaign_count: int = 0
    all_integrity_ok: bool = True
    all_falsification_complete: bool = True
    summary_statistics: dict = field(default_factory=dict)
    regression_thresholds: dict = field(default_factory=dict)
    review_label_status: dict = field(default_factory=dict)
    best_champion: dict = field(default_factory=dict)
    weakest_champion: dict = field(default_factory=dict)
    is_read_only: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "baseline_id": self.baseline_id,
            "baseline_name": self.baseline_name,
            "baseline_type": self.baseline_type,
            "frozen_at": self.frozen_at,
            "branch": self.branch,
            "commit": self.commit,
            "schema_version": self.schema_version,
            "profile": self.profile,
            "domain": self.domain,
            "generation_model": self.generation_model,
            "embedding_model": self.embedding_model,
            "champion_policy": self.champion_policy,
            "batch_id": self.batch_id,
            "campaign_ids": self.campaign_ids,
            "campaign_count": self.campaign_count,
            "all_integrity_ok": self.all_integrity_ok,
            "all_falsification_complete": self.all_falsification_complete,
            "summary_statistics": self.summary_statistics,
            "regression_thresholds": self.regression_thresholds,
            "review_label_status": self.review_label_status,
            "best_champion": self.best_champion,
            "weakest_champion": self.weakest_champion,
            "is_read_only": self.is_read_only,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewedBaseline":
        return cls(
            baseline_id=d.get("baseline_id", ""),
            baseline_name=d.get("baseline_name", ""),
            baseline_type=d.get("baseline_type", "reviewed_evaluation"),
            frozen_at=d.get("frozen_at", ""),
            branch=d.get("branch", ""),
            commit=d.get("commit", ""),
            schema_version=d.get("schema_version", ""),
            profile=d.get("profile", ""),
            domain=d.get("domain", ""),
            generation_model=d.get("generation_model", ""),
            embedding_model=d.get("embedding_model", ""),
            champion_policy=d.get("champion_policy", ""),
            batch_id=d.get("batch_id", ""),
            campaign_ids=d.get("campaign_ids", []),
            campaign_count=d.get("campaign_count", 0),
            all_integrity_ok=d.get("all_integrity_ok", True),
            all_falsification_complete=d.get("all_falsification_complete", True),
            summary_statistics=d.get("summary_statistics", {}),
            regression_thresholds=d.get("regression_thresholds", {}),
            review_label_status=d.get("review_label_status", {}),
            best_champion=d.get("best_champion", {}),
            weakest_champion=d.get("weakest_champion", {}),
            is_read_only=d.get("is_read_only", True),
            note=d.get("note", ""),
        )


# ---------------------------------------------------------------------------
# Baseline Registry
# ---------------------------------------------------------------------------

class BaselineRegistry:
    """Manages frozen trusted baselines for comparison."""

    def __init__(self, baselines_dir: Optional[str] = None):
        self.baselines_dir = baselines_dir or BASELINES_DIR

    def load(self, baseline_id: str) -> Optional[ReviewedBaseline]:
        """Load a baseline by ID. Returns None if not found."""
        filename = KNOWN_BASELINES.get(baseline_id)
        if filename is None:
            # Try loading by filename directly
            filename = f"{baseline_id}.json"

        path = os.path.join(self.baselines_dir, filename)
        if not os.path.exists(path):
            logger.warning("Baseline file not found: %s", path)
            return None

        with open(path) as f:
            data = json.load(f)

        # Handle phase5_validated which has a different schema
        if baseline_id == "phase5_validated" and "baseline_id" not in data:
            return self._wrap_phase5_baseline(data, path)

        return ReviewedBaseline.from_dict(data)

    def _wrap_phase5_baseline(self, data: dict, path: str) -> ReviewedBaseline:
        """Wrap the Phase 5 benchmark JSON into a ReviewedBaseline."""
        metrics = data.get("metrics", {})
        return ReviewedBaseline(
            baseline_id="phase5_validated",
            baseline_name="Phase 5 Validated Baseline",
            baseline_type="deterministic_benchmark",
            frozen_at=data.get("created", "2026-03-08T00:00:00Z"),
            branch="breakthrough-engine-phase5-validated",
            commit=data.get("commit", "29d68a39"),
            schema_version="benchmark_v1",
            profile="deterministic_test",
            domain="clean-energy",
            generation_model="FakeCandidateGenerator",
            embedding_model="MockEmbeddingProvider",
            champion_policy="phase5_champion",
            batch_id="phase5_validated_benchmark",
            campaign_ids=[],
            campaign_count=data.get("config", {}).get("n_runs", 3),
            all_integrity_ok=True,
            all_falsification_complete=True,
            summary_statistics={
                "draft_creation_rate": metrics.get("draft_creation_rate", 1.0),
                "novelty_block_rate": metrics.get("novelty_block_rate", 0.0),
                "synthesis_fit_pass_rate": metrics.get("synthesis_fit_pass_rate", 1.0),
                "review_worthy_rate": metrics.get("review_worthy_rate", 1.0),
                "top_candidate_final_score": metrics.get("top_candidate_final_score", 0.912),
                "mean_evidence_balance": metrics.get("mean_evidence_balance", 0.918),
            },
            regression_thresholds={
                "draft_creation_rate": -0.05,
                "novelty_block_rate": 0.05,
                "synthesis_fit_pass_rate": -0.05,
                "review_worthy_rate": -0.05,
                "top_candidate_final_score": -0.05,
                "mean_evidence_balance": -0.05,
            },
            review_label_status={"note": "Phase 5 is deterministic benchmark; no reviewer labels"},
            is_read_only=True,
            note="Phase 5 frozen benchmark. Use for algorithmic regression testing only.",
        )

    def list_baselines(self) -> list[dict]:
        """List all known baselines with brief metadata."""
        result = []
        for baseline_id, filename in KNOWN_BASELINES.items():
            path = os.path.join(self.baselines_dir, filename)
            exists = os.path.exists(path)
            entry = {
                "baseline_id": baseline_id,
                "filename": filename,
                "exists": exists,
                "path": path,
            }
            if exists:
                b = self.load(baseline_id)
                if b:
                    entry["baseline_name"] = b.baseline_name
                    entry["baseline_type"] = b.baseline_type
                    entry["frozen_at"] = b.frozen_at
                    entry["commit"] = b.commit
                    entry["campaign_count"] = b.campaign_count
            result.append(entry)
        return result

    def compare_batch_to_reviewed_baseline(
        self,
        batch_summary: dict,
        baseline_id: str = "phase7d_reviewed",
    ) -> dict:
        """Compare a batch summary to the Phase 7D reviewed baseline.

        Returns a comparison report with per-metric status.
        """
        baseline = self.load(baseline_id)
        if baseline is None:
            return {"error": f"Baseline '{baseline_id}' not found", "ok": False}

        base_stats = baseline.summary_statistics
        thresholds = baseline.regression_thresholds
        batch_stats = batch_summary.get("summary_statistics", {})

        comparisons = []
        regression_found = False

        metrics_to_compare = [
            ("champion_score_mean", "higher_better"),
            ("integrity_ok_rate", "higher_better"),
            ("falsification_complete_rate", "higher_better"),
            ("overall_block_rate", "lower_better"),
        ]

        for metric, direction in metrics_to_compare:
            baseline_val = base_stats.get(metric)
            current_val = batch_stats.get(metric)

            if baseline_val is None or current_val is None:
                comparisons.append({
                    "metric": metric,
                    "baseline": baseline_val,
                    "current": current_val,
                    "delta": None,
                    "status": "skipped",
                    "reason": "missing data",
                })
                continue

            delta = current_val - baseline_val
            threshold = thresholds.get(metric, -0.05)

            if direction == "higher_better":
                regressed = delta < threshold
            else:
                # lower_better: regression if current is much higher than baseline
                regressed = delta > abs(threshold)

            if regressed:
                regression_found = True

            comparisons.append({
                "metric": metric,
                "baseline": round(baseline_val, 4),
                "current": round(current_val, 4),
                "delta": round(delta, 4),
                "threshold": threshold,
                "direction": direction,
                "status": "REGRESSION" if regressed else "OK",
            })

        return {
            "baseline_id": baseline_id,
            "baseline_commit": baseline.commit,
            "baseline_campaign_count": baseline.campaign_count,
            "current_campaign_count": batch_summary.get("campaign_count", 0),
            "comparisons": comparisons,
            "regression_found": regression_found,
            "ok": not regression_found,
        }


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def get_registry(baselines_dir: Optional[str] = None) -> BaselineRegistry:
    """Get a baseline registry instance."""
    return BaselineRegistry(baselines_dir=baselines_dir)


def load_phase7d_reviewed_baseline(baselines_dir: Optional[str] = None) -> Optional[ReviewedBaseline]:
    """Load the Phase 7D reviewed baseline."""
    return get_registry(baselines_dir).load("phase7d_reviewed")


def load_phase5_validated_baseline(baselines_dir: Optional[str] = None) -> Optional[ReviewedBaseline]:
    """Load the Phase 5 validated baseline."""
    return get_registry(baselines_dir).load("phase5_validated")
