#!/usr/bin/env python3
"""Create frozen Phase 5 baseline artifact.

This script runs the benchmark harness in DETERMINISTIC_TEST mode
(FakeCandidateGenerator + MockEmbeddingProvider + in-memory DB)
and saves the resulting metrics as a frozen JSON artifact tied to the
validated Phase 5 tag (breakthrough-engine-phase5-validated).

The artifact is committed to the phase6 branch and treated as read-only
going forward.  All future Phase 6 comparisons reference this frozen file.

Usage:
    python scripts/create_phase5_baseline_artifact.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure we can import breakthrough_engine from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from breakthrough_engine.benchmark import (
    BenchmarkCandidateGenerator,
    golden_high_quality,
    golden_publishable_finalist,
    golden_overconfident,
    golden_evidence_poor,
    _make_deterministic_orchestrator,
)
from breakthrough_engine.db import init_db, Repository
from breakthrough_engine.embeddings import MockEmbeddingProvider
from breakthrough_engine.models import (
    CandidateStatus,
    ResearchProgram,
    RunMode,
    RunStatus,
)


BASELINE_PATH = Path(__file__).parent.parent / "runtime" / "baselines" / "phase5_validated_benchmark.json"
PHASE5_TAG = "breakthrough-engine-phase5-validated"


def _get_git_info() -> dict:
    """Return current git tag info."""
    def run(cmd):
        try:
            return subprocess.check_output(cmd, cwd=Path(__file__).parent.parent,
                                          stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            return ""

    return {
        "tag": PHASE5_TAG,
        "commit": run(["git", "rev-parse", PHASE5_TAG]),
        "current_branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "current_commit": run(["git", "rev-parse", "HEAD"]),
    }


def run_baseline_benchmark(n_runs: int = 3) -> dict:
    """Run multiple benchmark trials and aggregate metrics.

    Returns raw counts (not rates) so downstream Bayesian updates are clean.
    """
    # Fixed benchmark program config (matches benchmark_p6.yaml)
    program = ResearchProgram(
        name="benchmark_p6",
        domain="clean-energy",
        mode=RunMode.DETERMINISTIC_TEST,
        candidate_budget=5,
        simulation_budget=3,
        publication_threshold=0.60,
        evidence_minimum=2,
    )

    # Use fixed golden candidates for reproducibility
    golden_candidates = [
        golden_high_quality(),
        golden_publishable_finalist(),
        golden_overconfident(),
        golden_evidence_poor(),
    ]

    # Aggregate across runs
    total_draft_creation = 0
    total_novelty_pass = 0
    total_novelty_total = 0
    total_synthesis_fit_pass = 0
    total_synthesis_fit_total = 0
    total_review_worthy = 0
    total_review_worthy_denom = 0
    all_final_scores: list[float] = []
    all_evidence_balance: list[float] = []
    run_ids: list[str] = []
    elapsed_total = 0.0

    for trial_idx in range(n_runs):
        t0 = time.time()
        # Fresh in-memory DB per trial for isolation
        db = init_db(in_memory=True)
        repo = Repository(db)

        gen = BenchmarkCandidateGenerator(golden_candidates)
        orch, _ = _make_deterministic_orchestrator(
            program=program,
            generator=gen,
        )
        # Replace repo to use our isolated one
        orch.repo = repo
        from breakthrough_engine.memory import RunMemory
        orch.memory = RunMemory(repo.db)
        from breakthrough_engine.novelty import NoveltyEngine
        orch.novelty_engine = NoveltyEngine(repo.db)
        from breakthrough_engine.embedding_monitor import EmbeddingMonitor
        orch.embedding_monitor = EmbeddingMonitor(repo)
        from breakthrough_engine.diversity import DiversityEngine
        orch.diversity_engine = DiversityEngine(repo)
        from breakthrough_engine.corpus_manager import CorpusManager
        orch.corpus_manager = CorpusManager(repo)
        from breakthrough_engine.synthesis import SynthesisEngine
        orch.synthesis_engine = SynthesisEngine(repo)

        run = orch.run()
        elapsed = time.time() - t0
        elapsed_total += elapsed
        run_ids.append(run.id)

        # Draft creation (run-level binary)
        total_draft_creation += 1 if run.status == RunStatus.COMPLETED else 0

        # Candidate-level metrics
        candidates = repo.list_candidates_for_run(run.id)
        for c in candidates:
            status = c.get("status", "")
            # Novelty
            if status not in (CandidateStatus.NOVELTY_FAILED.value,
                              CandidateStatus.DEDUP_REJECTED.value):
                total_novelty_pass += 1
            total_novelty_total += 1

            # Get score
            score_row = repo.get_score(c["id"])
            if score_row:
                fs = score_row.get("final_score", 0.0)
                all_final_scores.append(float(fs))
                if fs >= 0.60:
                    total_review_worthy += 1
                total_review_worthy_denom += 1
                # Evidence balance (use evidence_strength_score as proxy)
                eb = score_row.get("evidence_strength_score", 0.0)
                all_evidence_balance.append(float(eb))

            # Synthesis fit (use all non-dedup-rejected)
            if status not in (CandidateStatus.DEDUP_REJECTED.value,
                              CandidateStatus.HYPOTHESIS_FAILED.value):
                synth_row = repo.get_synthesis_fit(c["id"])
                if synth_row is not None:
                    total_synthesis_fit_total += 1
                    if synth_row.get("passed", 1):
                        total_synthesis_fit_pass += 1
                else:
                    # Non-synthesis run: treat as pass
                    total_synthesis_fit_pass += 1
                    total_synthesis_fit_total += 1

        print(f"  Trial {trial_idx + 1}/{n_runs}: run={run.id[:8]} "
              f"status={run.status.value} elapsed={elapsed:.1f}s")

    return {
        "n_runs": n_runs,
        "run_ids": run_ids,
        "draft_creation": total_draft_creation,
        "draft_creation_denominator": n_runs,
        "novelty_pass_count": total_novelty_pass,
        "novelty_total_count": total_novelty_total,
        "synthesis_fit_pass_count": total_synthesis_fit_pass,
        "synthesis_fit_total_count": total_synthesis_fit_total,
        "review_worthy_count": total_review_worthy,
        "review_worthy_denominator": total_review_worthy_denom,
        "final_scores": all_final_scores,
        "evidence_balance_scores": all_evidence_balance,
        "elapsed_seconds": elapsed_total,
        "benchmark_config": {
            "seed": 42,
            "domain": "clean-energy",
            "candidate_budget": 5,
            "evidence_minimum": 2,
            "publication_threshold": 0.60,
            "n_runs": n_runs,
        },
    }


def main():
    if BASELINE_PATH.exists():
        print(f"Baseline artifact already exists at {BASELINE_PATH}")
        print("Delete it first if you want to regenerate.")
        with open(BASELINE_PATH) as f:
            existing = json.load(f)
        print(f"Existing baseline: tag={existing.get('baseline_tag')} "
              f"commit={existing.get('baseline_commit', '')[:8]}")
        return

    print(f"Creating Phase 5 baseline artifact from tag: {PHASE5_TAG}")
    git_info = _get_git_info()
    print(f"  Phase 5 commit: {git_info['commit'][:12] if git_info['commit'] else 'unknown'}")
    print(f"  Current branch: {git_info['current_branch']}")
    print()
    print("Running 3 benchmark trials (DETERMINISTIC_TEST, offline-safe)...")

    metrics = run_baseline_benchmark(n_runs=3)

    artifact = {
        "schema_version": 1,
        "baseline_tag": PHASE5_TAG,
        "baseline_commit": git_info["commit"],
        "created_on_branch": git_info["current_branch"],
        "created_at_commit": git_info["current_commit"],
        **metrics,
    }

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_PATH, "w") as f:
        json.dump(artifact, f, indent=2)

    # Derived rates for display
    dr = metrics["draft_creation"] / max(metrics["draft_creation_denominator"], 1)
    nbr = 1 - metrics["novelty_pass_count"] / max(metrics["novelty_total_count"], 1)
    sfr = metrics["synthesis_fit_pass_count"] / max(metrics["synthesis_fit_total_count"], 1)
    rwr = metrics["review_worthy_count"] / max(metrics["review_worthy_denominator"], 1)
    top = max(metrics["final_scores"]) if metrics["final_scores"] else 0.0
    eb_mean = (sum(metrics["evidence_balance_scores"]) /
               max(len(metrics["evidence_balance_scores"]), 1))

    print()
    print("=== Phase 5 Baseline Metrics ===")
    print(f"  Draft creation rate:      {dr:.2%}  ({metrics['draft_creation']}/{metrics['draft_creation_denominator']} runs)")
    print(f"  Novelty block rate:       {nbr:.2%}  ({metrics['novelty_total_count'] - metrics['novelty_pass_count']}/{metrics['novelty_total_count']} candidates)")
    print(f"  Synthesis fit pass rate:  {sfr:.2%}  ({metrics['synthesis_fit_pass_count']}/{metrics['synthesis_fit_total_count']} candidates)")
    print(f"  Review-worthy rate:       {rwr:.2%}  ({metrics['review_worthy_count']}/{metrics['review_worthy_denominator']} candidates)")
    print(f"  Top candidate score:      {top:.3f}")
    print(f"  Mean evidence balance:    {eb_mean:.3f}")
    print()
    print(f"Artifact saved to: {BASELINE_PATH}")
    print("Commit this file to the phase6 branch to freeze it.")


if __name__ == "__main__":
    main()
