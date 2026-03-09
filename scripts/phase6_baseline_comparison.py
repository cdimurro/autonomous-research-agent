#!/usr/bin/env python3
"""Phase 6 baseline comparison validation script.

Runs the benchmark harness in DETERMINISTIC_TEST mode and compares against
the frozen Phase 5 baseline artifact at runtime/baselines/phase5_validated_benchmark.json.

Usage:
    python scripts/phase6_baseline_comparison.py [--save]

Flags:
    --save    Save comparison report to database
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
from breakthrough_engine.db import init_db, Repository


def main():
    parser = argparse.ArgumentParser(description="Phase 6 baseline comparison")
    parser.add_argument("--save", action="store_true", help="Save comparison report to database")
    parser.add_argument("--n-runs", type=int, default=3, help="Number of benchmark trials (default: 3)")
    args = parser.parse_args()

    print("Phase 6 Baseline Comparison")
    print("=" * 55)

    # Load frozen baseline
    comp = BaselineComparator()
    try:
        baseline = comp.load_phase5_baseline()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Run scripts/create_phase5_baseline_artifact.py first to create the frozen baseline.")
        sys.exit(1)

    print(f"Baseline: tag={baseline.baseline_tag} commit={baseline.baseline_commit[:12]}")
    print()

    # Run benchmark
    db = init_db(in_memory=True)
    repo = Repository(db)
    config = BenchmarkConfig(n_runs=args.n_runs)

    print(f"Running {args.n_runs} benchmark trial(s) (DETERMINISTIC_TEST, offline-safe)...")
    current = comp.run_benchmark(config, repo)
    print()

    # Compare
    report = comp.compare(baseline, current)
    print(comp.format_report(report))

    if args.save:
        # Use real DB for saving
        db2 = init_db()
        repo2 = Repository(db2)
        comp.save_comparison(repo2, report)
        print("Comparison report saved to database.")

    if report.has_regression:
        print("\nWARNING: Regression detected. This branch does NOT meet Phase 5 baseline.")
        sys.exit(1)
    else:
        print("\nSUCCESS: No regressions. Branch is at or above Phase 5 baseline.")
        sys.exit(0)


if __name__ == "__main__":
    main()
