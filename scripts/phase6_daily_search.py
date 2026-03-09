#!/usr/bin/env python3
"""Phase 6 daily search campaign validation script.

Runs the 5-stage quality-first search ladder and prints a campaign report.
By default runs in benchmark mode (offline-safe, deterministic).

Usage:
    # Benchmark mode (offline-safe, fast)
    python scripts/phase6_daily_search.py --mode benchmark

    # Production mode (requires Ollama)
    python scripts/phase6_daily_search.py --mode production --budget 30

Flags:
    --mode MODE      benchmark (default) or production
    --budget MINUTES Wall-clock budget in minutes (production only, default: 30)
    --policy ID      Policy ID to use (default: champion)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
from breakthrough_engine.policy_registry import PolicyRegistry
from breakthrough_engine.db import init_db, Repository
from breakthrough_engine.config_loader import load_program


def main():
    parser = argparse.ArgumentParser(description="Phase 6 daily search campaign")
    parser.add_argument("--mode", default="benchmark", choices=["benchmark", "production"],
                        help="Campaign mode (default: benchmark)")
    parser.add_argument("--budget", type=int, default=30,
                        help="Wall-clock budget in minutes (production only, default: 30)")
    parser.add_argument("--policy", default=None, help="Policy ID (default: champion)")
    args = parser.parse_args()

    print("Phase 6 Daily Search Campaign")
    print("=" * 55)
    print(f"Mode: {args.mode}")

    db = init_db(in_memory=True)
    repo = Repository(db)

    # Load program
    try:
        program_name = "benchmark_p6" if args.mode == "benchmark" else "daily_quality"
        program = load_program(program_name)
    except FileNotFoundError:
        print(f"Program '{program_name}' not found, falling back to general_fast_loop")
        program = load_program("general_fast_loop")

    # Configure ladder
    config = LadderConfig(mode=args.mode)
    if args.mode == "production":
        config.production_wall_clock_budget_minutes = args.budget
    if args.policy:
        config.policy_variants = [args.policy]

    registry = PolicyRegistry(repo)
    ladder = DailySearchLadder()

    print(f"Program: {program.name} (domain={program.domain})")
    print()

    result = ladder.run_campaign(repo, config, registry, program)

    print(f"Campaign ID: {result.campaign_id}")
    print(f"Policy used: {result.policy_used}")
    print(f"Elapsed: {result.elapsed_seconds:.1f}s")
    print()

    print("Stage Results:")
    print("-" * 55)
    for stage in result.ladder_stages:
        print(f"  {stage.stage_name}:")
        print(f"    Stop reason: {stage.stop_reason}")
        print(f"    Trials: {stage.trials_attempted}")
        print(f"    Advanced: {stage.candidates_advanced}  Abandoned: {stage.candidates_abandoned}")
        print(f"    Best score: {stage.best_score:.3f}")
    print()

    print("Campaign Summary:")
    print("-" * 55)
    print(f"  Candidates generated: {result.total_candidates_generated}")
    print(f"  Blocked: {result.total_blocked}")
    print(f"  Shortlisted: {result.total_shortlisted}")
    print(f"  Daily champion: {result.daily_champion_id or 'none'}")
    if result.daily_champion_title:
        print(f"  Champion title: {result.daily_champion_title}")
    print(f"  Rationale: {result.champion_selection_rationale}")

    if result.daily_champion_id:
        print("\nSUCCESS: Daily champion selected.")
        sys.exit(0)
    else:
        print("\nWARNING: No daily champion selected (all stages abandoned or no candidates passed).")
        sys.exit(1)


if __name__ == "__main__":
    main()
