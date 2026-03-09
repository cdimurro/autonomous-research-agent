"""Baseline comparison harness for Breakthrough Engine Phase 6.

Compares the current system against the frozen Phase 5 validated baseline
artifact. The baseline artifact is a committed JSON file created from the
`breakthrough-engine-phase5-validated` tag — it is read-only.

Key design:
- BenchmarkMetrics stores raw COUNTS (not rates), so Bayesian updates downstream
  receive correct observation units.
- Derived rates (novelty_block_rate etc.) are computed on demand from counts.
- The comparison report stores deltas and regression flags but NOT a second
  copy of raw metrics — that avoids semantic duplication.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .benchmark import BenchmarkCandidateGenerator, _make_deterministic_orchestrator
from .benchmark import (
    golden_high_quality,
    golden_publishable_finalist,
    golden_overconfident,
    golden_evidence_poor,
)
from .db import Repository, init_db
from .models import CandidateStatus, ResearchProgram, RunMode, RunStatus, new_id

logger = logging.getLogger(__name__)

BASELINE_PATH = Path(__file__).parent.parent / "runtime" / "baselines" / "phase5_validated_benchmark.json"
PHASE5_TAG = "breakthrough-engine-phase5-validated"
REGRESSION_THRESHOLD = 0.05


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_git_info() -> dict:
    """Return current branch and commit hash."""
    def run(cmd):
        try:
            return subprocess.check_output(
                cmd, cwd=Path(__file__).parent.parent, stderr=subprocess.DEVNULL
            ).decode().strip()
        except Exception:
            return ""

    return {
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": run(["git", "rev-parse", "HEAD"]),
    }


# ---------------------------------------------------------------------------
# BenchmarkConfig
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkConfig:
    """Fixed configuration for reproducible benchmark runs."""
    seed: int = 42
    domain: str = "clean-energy"
    candidate_budget: int = 5
    evidence_minimum: int = 2
    publication_threshold: float = 0.60
    n_runs: int = 3
    program_name: str = "benchmark_p6"


# ---------------------------------------------------------------------------
# BenchmarkMetrics
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkMetrics:
    """Raw counts (not rates) from a benchmark run.

    Stores counts so downstream Bayesian updates receive correct units.
    Derived rates are computed as properties.
    """
    # Run-level binary
    draft_creation: int = 0
    draft_creation_denominator: int = 0

    # Candidate-level binary
    novelty_pass_count: int = 0
    novelty_total_count: int = 0

    synthesis_fit_pass_count: int = 0
    synthesis_fit_total_count: int = 0

    review_worthy_count: int = 0
    review_worthy_denominator: int = 0

    # Continuous (per-candidate values)
    final_scores: list = field(default_factory=list)
    evidence_balance_scores: list = field(default_factory=list)

    # Metadata
    run_id: str = ""
    elapsed_seconds: float = 0.0
    baseline_tag: str = ""
    baseline_commit: str = ""
    benchmark_config: dict = field(default_factory=dict)

    # Derived rates (computed from counts)
    @property
    def draft_creation_rate(self) -> float:
        return self.draft_creation / max(self.draft_creation_denominator, 1)

    @property
    def novelty_block_rate(self) -> float:
        blocked = self.novelty_total_count - self.novelty_pass_count
        return blocked / max(self.novelty_total_count, 1)

    @property
    def synthesis_fit_pass_rate(self) -> float:
        return self.synthesis_fit_pass_count / max(self.synthesis_fit_total_count, 1)

    @property
    def review_worthy_rate(self) -> float:
        return self.review_worthy_count / max(self.review_worthy_denominator, 1)

    @property
    def top_candidate_final_score(self) -> float:
        return max(self.final_scores) if self.final_scores else 0.0

    @property
    def mean_evidence_balance(self) -> float:
        if not self.evidence_balance_scores:
            return 0.0
        return sum(self.evidence_balance_scores) / len(self.evidence_balance_scores)

    @property
    def operator_burden_proxy(self) -> float:
        return 1.0 - self.draft_creation_rate

    def to_dict(self) -> dict:
        return {
            "draft_creation": self.draft_creation,
            "draft_creation_denominator": self.draft_creation_denominator,
            "novelty_pass_count": self.novelty_pass_count,
            "novelty_total_count": self.novelty_total_count,
            "synthesis_fit_pass_count": self.synthesis_fit_pass_count,
            "synthesis_fit_total_count": self.synthesis_fit_total_count,
            "review_worthy_count": self.review_worthy_count,
            "review_worthy_denominator": self.review_worthy_denominator,
            "final_scores": self.final_scores,
            "evidence_balance_scores": self.evidence_balance_scores,
            "run_id": self.run_id,
            "elapsed_seconds": self.elapsed_seconds,
            "baseline_tag": self.baseline_tag,
            "baseline_commit": self.baseline_commit,
            "benchmark_config": self.benchmark_config,
            # Derived rates for convenience
            "draft_creation_rate": round(self.draft_creation_rate, 4),
            "novelty_block_rate": round(self.novelty_block_rate, 4),
            "synthesis_fit_pass_rate": round(self.synthesis_fit_pass_rate, 4),
            "review_worthy_rate": round(self.review_worthy_rate, 4),
            "top_candidate_final_score": round(self.top_candidate_final_score, 4),
            "mean_evidence_balance": round(self.mean_evidence_balance, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BenchmarkMetrics":
        return cls(
            draft_creation=d.get("draft_creation", 0),
            draft_creation_denominator=d.get("draft_creation_denominator", 0),
            novelty_pass_count=d.get("novelty_pass_count", 0),
            novelty_total_count=d.get("novelty_total_count", 0),
            synthesis_fit_pass_count=d.get("synthesis_fit_pass_count", 0),
            synthesis_fit_total_count=d.get("synthesis_fit_total_count", 0),
            review_worthy_count=d.get("review_worthy_count", 0),
            review_worthy_denominator=d.get("review_worthy_denominator", 0),
            final_scores=d.get("final_scores", []),
            evidence_balance_scores=d.get("evidence_balance_scores", []),
            run_id=d.get("run_id", ""),
            elapsed_seconds=d.get("elapsed_seconds", 0.0),
            baseline_tag=d.get("baseline_tag", ""),
            baseline_commit=d.get("baseline_commit", ""),
            benchmark_config=d.get("benchmark_config", {}),
        )


# ---------------------------------------------------------------------------
# ComparisonReport
# ---------------------------------------------------------------------------

@dataclass
class MetricComparison:
    name: str
    baseline_value: float
    current_value: float
    delta: float
    is_regression: bool
    regression_threshold: float = REGRESSION_THRESHOLD
    note: str = ""


@dataclass
class ComparisonReport:
    baseline_tag: str
    baseline_commit: str
    current_branch: str
    current_commit: str
    metrics: list = field(default_factory=list)
    has_regression: bool = False
    summary: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "baseline_tag": self.baseline_tag,
            "baseline_commit": self.baseline_commit,
            "current_branch": self.current_branch,
            "current_commit": self.current_commit,
            "metrics": [
                {
                    "name": m.name,
                    "baseline": round(m.baseline_value, 4),
                    "current": round(m.current_value, 4),
                    "delta": round(m.delta, 4),
                    "is_regression": m.is_regression,
                    "note": m.note,
                }
                for m in self.metrics
            ],
            "has_regression": self.has_regression,
            "summary": self.summary,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# BaselineComparator
# ---------------------------------------------------------------------------

class BaselineComparator:
    """Runs benchmark episodes and compares against the frozen Phase 5 baseline."""

    def run_benchmark(
        self,
        config: Optional[BenchmarkConfig] = None,
        repo: Optional[Repository] = None,
    ) -> BenchmarkMetrics:
        """Run N benchmark trials and return aggregated metrics.

        Uses DETERMINISTIC_TEST mode (FakeCandidateGenerator, in-memory DB).
        Offline-safe.
        """
        if config is None:
            config = BenchmarkConfig()

        program = ResearchProgram(
            name=config.program_name,
            domain=config.domain,
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=config.candidate_budget,
            simulation_budget=3,
            publication_threshold=config.publication_threshold,
            evidence_minimum=config.evidence_minimum,
        )

        golden_candidates = [
            golden_high_quality(),
            golden_publishable_finalist(),
            golden_overconfident(),
            golden_evidence_poor(),
        ]

        total_draft_creation = 0
        total_novelty_pass = 0
        total_novelty_total = 0
        total_synthesis_fit_pass = 0
        total_synthesis_fit_total = 0
        total_review_worthy = 0
        total_review_worthy_denom = 0
        all_final_scores: list = []
        all_evidence_balance: list = []
        last_run_id = ""
        t0 = time.time()

        for trial_idx in range(config.n_runs):
            trial_db = init_db(in_memory=True)
            trial_repo = Repository(trial_db)

            gen = BenchmarkCandidateGenerator(golden_candidates)
            orch, _ = _make_deterministic_orchestrator(
                program=program,
                generator=gen,
            )
            # Use isolated repo
            orch.repo = trial_repo
            from .memory import RunMemory
            from .novelty import NoveltyEngine
            from .embedding_monitor import EmbeddingMonitor
            from .diversity import DiversityEngine
            from .corpus_manager import CorpusManager
            from .synthesis import SynthesisEngine
            orch.memory = RunMemory(trial_repo.db)
            orch.novelty_engine = NoveltyEngine(trial_repo.db)
            orch.embedding_monitor = EmbeddingMonitor(trial_repo)
            orch.diversity_engine = DiversityEngine(trial_repo)
            orch.corpus_manager = CorpusManager(trial_repo)
            orch.synthesis_engine = SynthesisEngine(trial_repo)

            run = orch.run()
            last_run_id = run.id
            total_draft_creation += 1 if run.status == RunStatus.COMPLETED else 0

            for c in trial_repo.list_candidates_for_run(run.id):
                status = c.get("status", "")

                if status not in (CandidateStatus.NOVELTY_FAILED.value,
                                  CandidateStatus.DEDUP_REJECTED.value):
                    total_novelty_pass += 1
                total_novelty_total += 1

                score_row = trial_repo.get_score(c["id"])
                if score_row:
                    fs = float(score_row.get("final_score", 0.0))
                    all_final_scores.append(fs)
                    if fs >= config.publication_threshold:
                        total_review_worthy += 1
                    total_review_worthy_denom += 1
                    eb = float(score_row.get("evidence_strength_score", 0.0))
                    all_evidence_balance.append(eb)

                if status not in (CandidateStatus.DEDUP_REJECTED.value,
                                  CandidateStatus.HYPOTHESIS_FAILED.value):
                    synth_row = trial_repo.get_synthesis_fit(c["id"])
                    if synth_row is not None:
                        total_synthesis_fit_total += 1
                        if synth_row.get("passed", 1):
                            total_synthesis_fit_pass += 1
                    else:
                        total_synthesis_fit_pass += 1
                        total_synthesis_fit_total += 1

        elapsed = time.time() - t0
        return BenchmarkMetrics(
            draft_creation=total_draft_creation,
            draft_creation_denominator=config.n_runs,
            novelty_pass_count=total_novelty_pass,
            novelty_total_count=total_novelty_total,
            synthesis_fit_pass_count=total_synthesis_fit_pass,
            synthesis_fit_total_count=total_synthesis_fit_total,
            review_worthy_count=total_review_worthy,
            review_worthy_denominator=total_review_worthy_denom,
            final_scores=all_final_scores,
            evidence_balance_scores=all_evidence_balance,
            run_id=last_run_id,
            elapsed_seconds=elapsed,
            benchmark_config={
                "seed": config.seed,
                "domain": config.domain,
                "candidate_budget": config.candidate_budget,
                "evidence_minimum": config.evidence_minimum,
                "publication_threshold": config.publication_threshold,
                "n_runs": config.n_runs,
            },
        )

    def load_phase5_baseline(self) -> BenchmarkMetrics:
        """Load the frozen Phase 5 baseline artifact.

        Raises FileNotFoundError if the artifact does not exist —
        it must be committed to the repo before use.
        """
        if not BASELINE_PATH.exists():
            raise FileNotFoundError(
                f"Phase 5 baseline artifact not found at {BASELINE_PATH}. "
                "Run scripts/create_phase5_baseline_artifact.py to create it."
            )
        with open(BASELINE_PATH) as f:
            d = json.load(f)
        m = BenchmarkMetrics.from_dict(d)
        m.baseline_tag = d.get("baseline_tag", PHASE5_TAG)
        m.baseline_commit = d.get("baseline_commit", "")
        return m

    def compare(
        self,
        baseline: BenchmarkMetrics,
        current: BenchmarkMetrics,
    ) -> ComparisonReport:
        """Compare current metrics against baseline, return a ComparisonReport.

        The report stores deltas and regression flags but NOT a duplicate
        of the raw metric data.
        """
        git = _get_git_info()

        # Metrics to compare: (name, baseline_val, current_val, lower_is_better)
        comparisons_spec = [
            ("draft_creation_rate", baseline.draft_creation_rate, current.draft_creation_rate, False),
            ("novelty_block_rate", baseline.novelty_block_rate, current.novelty_block_rate, True),
            ("synthesis_fit_pass_rate", baseline.synthesis_fit_pass_rate, current.synthesis_fit_pass_rate, False),
            ("review_worthy_rate", baseline.review_worthy_rate, current.review_worthy_rate, False),
            ("top_candidate_final_score", baseline.top_candidate_final_score, current.top_candidate_final_score, False),
            ("mean_evidence_balance", baseline.mean_evidence_balance, current.mean_evidence_balance, False),
        ]

        metrics = []
        has_regression = False

        for name, base_val, curr_val, lower_is_better in comparisons_spec:
            delta = curr_val - base_val
            if lower_is_better:
                # Regression = current is HIGHER by more than threshold
                is_regression = delta > REGRESSION_THRESHOLD
            else:
                # Regression = current is LOWER by more than threshold
                is_regression = delta < -REGRESSION_THRESHOLD

            if is_regression:
                has_regression = True

            metrics.append(MetricComparison(
                name=name,
                baseline_value=base_val,
                current_value=curr_val,
                delta=delta,
                is_regression=is_regression,
                note="REGRESSION" if is_regression else ("↑" if delta > 0.01 else ("↓" if delta < -0.01 else "→")),
            ))

        if has_regression:
            summary = "REGRESSION DETECTED — champion rollback may be warranted"
        else:
            summary = "NO REGRESSION — system meets or exceeds Phase 5 baseline"

        return ComparisonReport(
            baseline_tag=baseline.baseline_tag or PHASE5_TAG,
            baseline_commit=baseline.baseline_commit,
            current_branch=git["branch"],
            current_commit=git["commit"],
            metrics=metrics,
            has_regression=has_regression,
            summary=summary,
            created_at=_utcnow(),
        )

    def save_comparison(self, repo: Repository, report: ComparisonReport) -> str:
        """Persist the comparison artifact to bt_baseline_comparisons.

        Stores the comparison RESULT only — not a second copy of raw metrics.
        """
        comparison_id = new_id()
        repo.db.execute(
            """INSERT INTO bt_baseline_comparisons
               (id, baseline_tag, baseline_commit, current_branch, current_commit,
                comparison_report_json, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                comparison_id,
                report.baseline_tag,
                report.baseline_commit,
                report.current_branch,
                report.current_commit,
                json.dumps(report.to_dict()),
                report.created_at or _utcnow(),
            ),
        )
        repo.db.commit()
        logger.info(
            "Saved baseline comparison %s (regression=%s)",
            comparison_id, report.has_regression,
        )
        return comparison_id

    def format_report(self, report: ComparisonReport) -> str:
        """Format a comparison report as a human-readable text table."""
        lines = [
            "Phase 6 Baseline Comparison Report",
            "=" * 60,
            f"Baseline: {report.baseline_tag} ({report.baseline_commit[:8] if report.baseline_commit else 'unknown'})",
            f"Current:  {report.current_branch} ({report.current_commit[:8] if report.current_commit else 'unknown'})",
            "",
            f"{'Metric':<35} {'Baseline':>10} {'Current':>10} {'Delta':>8} {'Status':>12}",
            "-" * 80,
        ]
        for m in report.metrics:
            status = "⚠ REGRESSION" if m.is_regression else m.note
            lines.append(
                f"{m.name:<35} {m.baseline_value:>10.4f} {m.current_value:>10.4f} "
                f"{m.delta:>+8.4f} {status:>12}"
            )
        lines += [
            "",
            f"Overall: {report.summary}",
        ]
        return "\n".join(lines)

    def rollback_if_regression(
        self, report: ComparisonReport, policy_registry
    ) -> bool:
        """If regression detected, trigger champion rollback.

        Returns True if rollback was triggered.
        """
        if report.has_regression:
            regression_metrics = [m.name for m in report.metrics if m.is_regression]
            reason = f"Benchmark regression detected in: {', '.join(regression_metrics)}"
            success, msg = policy_registry.rollback_champion(reason=reason)
            if success:
                logger.warning("Champion rolled back due to regression: %s", reason)
            else:
                logger.warning("Could not roll back champion: %s", msg)
            return True
        return False
