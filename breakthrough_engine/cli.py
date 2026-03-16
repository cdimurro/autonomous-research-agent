"""CLI entrypoints for the Breakthrough Engine.

Usage:
    python -m breakthrough_engine run [--program NAME] [--mode MODE]
    python -m breakthrough_engine list-publications
    python -m breakthrough_engine show-run RUN_ID
    python -m breakthrough_engine list-runs
    python -m breakthrough_engine validate-config NAME
    python -m breakthrough_engine list-programs
    python -m breakthrough_engine serve [--port PORT]
    python -m breakthrough_engine benchmark run
    python -m breakthrough_engine schedule run-once [--program NAME]
    python -m breakthrough_engine schedule generate-plist [--program NAME] [--hour H]
    python -m breakthrough_engine omniverse build-bundle --candidate-id ID
    python -m breakthrough_engine omniverse ingest-result PATH
    python -m breakthrough_engine review list
    python -m breakthrough_engine review show DRAFT_ID
    python -m breakthrough_engine review approve DRAFT_ID
    python -m breakthrough_engine review reject DRAFT_ID [--reason "..."]
    python -m breakthrough_engine metrics recent
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from .config_loader import list_programs, load_program, validate_program
from .db import Repository, init_db
from .orchestrator import BreakthroughOrchestrator
from .reporting import generate_markdown_report, save_reports

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="breakthrough_engine",
        description="Daily Breakthrough Candidate Engine",
    )
    parser.add_argument(
        "--db", default=None, help="Path to SQLite database (default: runtime/db/scires.db)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Run a breakthrough cycle")
    run_p.add_argument("--program", default="general_fast_loop", help="Research program name")
    run_p.add_argument("--mode", default=None, help="Override run mode")

    # list-publications
    sub.add_parser("list-publications", help="List published candidates")

    # show-run
    show_p = sub.add_parser("show-run", help="Show details of a run")
    show_p.add_argument("run_id", help="Run ID")

    # list-runs
    sub.add_parser("list-runs", help="List recent runs")

    # validate-config
    val_p = sub.add_parser("validate-config", help="Validate a research program config")
    val_p.add_argument("name", help="Program name (without .yaml)")

    # list-programs
    sub.add_parser("list-programs", help="List available research programs")

    # serve
    serve_p = sub.add_parser("serve", help="Start the API server")
    serve_p.add_argument("--port", type=int, default=8099, help="Port (default: 8099)")

    # benchmark
    bench_p = sub.add_parser("benchmark", help="Run benchmark suite")
    bench_sub = bench_p.add_subparsers(dest="bench_command")
    bench_sub.add_parser("run", help="Run the full benchmark suite")

    # schedule
    sched_p = sub.add_parser("schedule", help="Scheduler commands")
    sched_sub = sched_p.add_subparsers(dest="sched_command")
    sched_run_p = sched_sub.add_parser("run-once", help="Run a single scheduled cycle")
    sched_run_p.add_argument("--program", default="general_fast_loop", help="Research program name")
    sched_plist_p = sched_sub.add_parser("generate-plist", help="Generate launchd plist")
    sched_plist_p.add_argument("--program", default="general_fast_loop", help="Research program name")
    sched_plist_p.add_argument("--hour", type=int, default=6, help="Hour to run (0-23)")
    sched_plist_p.add_argument("--minute", type=int, default=0, help="Minute to run (0-59)")

    # omniverse
    omni_p = sub.add_parser("omniverse", help="Omniverse integration commands")
    omni_sub = omni_p.add_subparsers(dest="omni_command")
    omni_build_p = omni_sub.add_parser("build-bundle", help="Build an Omniverse execution bundle")
    omni_build_p.add_argument("--candidate-id", required=True, help="Candidate ID to build bundle for")
    omni_build_p.add_argument("--run-id", default=None, help="Run ID (to find candidate)")
    omni_ingest_p = omni_sub.add_parser("ingest-result", help="Ingest Omniverse simulation result")
    omni_ingest_p.add_argument("path", help="Path to result JSON file")

    # review (Phase 3)
    review_p = sub.add_parser("review", help="Operator review commands")
    review_sub = review_p.add_subparsers(dest="review_command")
    review_sub.add_parser("list", help="List drafts pending review")
    review_show_p = review_sub.add_parser("show", help="Show draft details")
    review_show_p.add_argument("draft_id", help="Draft ID")
    review_approve_p = review_sub.add_parser("approve", help="Approve a draft")
    review_approve_p.add_argument("draft_id", help="Draft ID")
    review_approve_p.add_argument("--notes", default="", help="Review notes")
    review_reject_p = review_sub.add_parser("reject", help="Reject a draft")
    review_reject_p.add_argument("draft_id", help="Draft ID")
    review_reject_p.add_argument("--reason", default="", help="Rejection reason")

    # metrics (Phase 3)
    metrics_p = sub.add_parser("metrics", help="Run metrics commands")
    metrics_sub = metrics_p.add_subparsers(dest="metrics_command")
    metrics_sub.add_parser("recent", help="Show recent run metrics")

    # doctor
    sub.add_parser("doctor", help="Check system readiness (Ollama, DB, models)")

    # Phase 6: baseline
    baseline_p = sub.add_parser("baseline", help="Phase 6 baseline comparison commands")
    baseline_sub = baseline_p.add_subparsers(dest="baseline_command")
    baseline_sub.add_parser("compare", help="Run benchmark and compare against Phase 5 baseline")

    # Phase 6: policy
    policy_p = sub.add_parser("policy", help="Phase 6 policy management commands")
    policy_sub = policy_p.add_subparsers(dest="policy_command")
    policy_sub.add_parser("list", help="List champion and challengers")
    policy_show_p = policy_sub.add_parser("show", help="Show policy config + trial history")
    policy_show_p.add_argument("policy_id", help="Policy ID")
    policy_promote_p = policy_sub.add_parser("promote", help="Promote challenger to probation/champion")
    policy_promote_p.add_argument("policy_id", help="Challenger policy ID")
    policy_promote_p.add_argument("--reason", default="", help="Promotion reason")
    policy_manual_promote_p = policy_sub.add_parser(
        "manual-promote",
        help="Manually promote a challenger directly to champion (bypasses trial count — use after external A/B trial)"
    )
    policy_manual_promote_p.add_argument("policy_id", help="Challenger policy ID to promote")
    policy_manual_promote_p.add_argument("--reason", required=True, help="Promotion reason (required)")
    policy_manual_promote_p.add_argument("--trial-id", default="", help="Trial ID supporting this promotion")
    policy_rollback_p = policy_sub.add_parser("rollback", help="Roll back champion to previous")
    policy_rollback_p.add_argument("--reason", default="", help="Rollback reason")
    # Phase 8B: register a challenger
    policy_register_p = policy_sub.add_parser("register", help="Register a challenger policy")
    policy_register_p.add_argument("--name", required=True, help="Policy name")
    policy_register_p.add_argument("--description", default="", help="Human-readable description")
    policy_register_p.add_argument("--config-path", default="", help="Path to policy JSON config file")
    policy_register_p.add_argument("--generation-prompt-variant", default="standard",
                                   choices=["standard", "synthesis_focus", "evidence_heavy"],
                                   help="Generation prompt variant (default: standard)")
    policy_register_p.add_argument("--diversity-steering-variant", default="standard",
                                   choices=["standard", "aggressive", "conservative"],
                                   help="Diversity steering variant (default: standard)")
    policy_register_p.add_argument("--negative-memory-strategy", default="standard",
                                   choices=["standard", "strict", "permissive"],
                                   help="Negative memory strategy (default: standard)")
    policy_register_p.add_argument("--scoring-weights-json", default="",
                                   help="JSON string of scoring weight overrides")

    # Phase 6: daily-search
    ds_p = sub.add_parser("daily-search", help="Phase 6 quality-first daily search ladder")
    ds_sub = ds_p.add_subparsers(dest="ds_command")
    ds_run_p = ds_sub.add_parser("run", help="Run a daily search campaign")
    ds_run_p.add_argument("--mode", default="benchmark", choices=["benchmark", "production"],
                          help="Campaign mode (default: benchmark)")
    ds_run_p.add_argument("--budget", type=int, default=30,
                          help="Wall-clock budget in minutes (production mode only, default: 30)")
    ds_run_p.add_argument("--policy", default=None, help="Policy ID to use (default: champion)")

    # Phase 6: cockpit
    cockpit_p = sub.add_parser("cockpit", help="Phase 6 review cockpit commands")
    cockpit_sub = cockpit_p.add_subparsers(dest="cockpit_command")
    cockpit_show_p = cockpit_sub.add_parser("show", help="Show review decision packet for a run")
    cockpit_show_p.add_argument("run_id", help="Run ID")

    # Phase 6: falsify
    falsify_p = sub.add_parser("falsify", help="Phase 6 run falsification on a candidate")
    falsify_p.add_argument("candidate_id", help="Candidate ID")

    # Phase 7A: preflight
    preflight_p = sub.add_parser("preflight", help="Phase 7A campaign preflight verification")
    preflight_p.add_argument("--strict", action="store_true", help="Strict mode (fail on any FAIL check)")
    preflight_p.add_argument("--profile", default="", help="Campaign profile name")

    # Phase 7A: campaign
    campaign_p = sub.add_parser("campaign", help="Phase 7A autonomous campaign management")
    campaign_sub = campaign_p.add_subparsers(dest="campaign_command")
    campaign_run_p = campaign_sub.add_parser("run", help="Launch an autonomous campaign")
    campaign_run_p.add_argument("--profile", default="pilot_30m",
                                help="Campaign profile (default: pilot_30m)")
    campaign_run_p.add_argument("--strict", action="store_true", default=True,
                                help="Strict preflight (default: yes)")
    campaign_run_p.add_argument("--dry-run", action="store_true",
                                help="Preflight only, do not execute")
    campaign_run_p.add_argument("--policy", default=None,
                                help="Policy ID to use instead of champion (for A/B trials)")
    campaign_list_p = campaign_sub.add_parser("list", help="List recent campaigns")
    campaign_list_p.add_argument("--limit", type=int, default=20, help="Max results")
    campaign_show_p = campaign_sub.add_parser("show", help="Show campaign receipt")
    campaign_show_p.add_argument("campaign_id", help="Campaign ID")
    campaign_sub.add_parser("profiles", help="List available campaign profiles")

    # Phase 7B: evaluation-pack
    ep_p = sub.add_parser("evaluation-pack", help="Phase 7B evaluation pack management")
    ep_sub = ep_p.add_subparsers(dest="ep_command")
    ep_export_p = ep_sub.add_parser("export", help="Export evaluation pack for a campaign")
    ep_export_p.add_argument("campaign_id", help="Campaign ID to export")
    ep_export_p.add_argument("--overwrite", action="store_true", help="Overwrite existing pack")
    ep_sub.add_parser("list", help="List existing evaluation packs")

    # Phase 7D: review-label
    rl_p = sub.add_parser("review-label", help="Phase 7D structured human review labels")
    rl_sub = rl_p.add_subparsers(dest="rl_command")
    rl_add_p = rl_sub.add_parser("add", help="Add a review label for a candidate")
    rl_add_p.add_argument("--campaign-id", required=True, help="Campaign ID")
    rl_add_p.add_argument("--candidate-id", required=True, help="Candidate ID")
    rl_add_p.add_argument("--candidate-title", default="", help="Candidate title (optional)")
    rl_add_p.add_argument("--role", default="finalist", choices=["champion", "runner_up", "finalist"], help="Candidate role")
    rl_add_p.add_argument("--decision", required=True, choices=["approve", "reject", "defer"], help="Review decision")
    rl_add_p.add_argument("--novelty-confidence", type=float, default=0.5, help="Novelty confidence 0.0-1.0")
    rl_add_p.add_argument("--technical-plausibility", type=float, default=0.5, help="Technical plausibility 0.0-1.0")
    rl_add_p.add_argument("--commercialization-relevance", type=float, default=0.5, help="Commercialization relevance 0.0-1.0")
    rl_add_p.add_argument("--key-flaw", default="", help="Primary weakness")
    rl_add_p.add_argument("--note", default="", help="Free-form reviewer note")
    rl_add_p.add_argument("--reviewer", default="operator", help="Reviewer identifier")
    rl_list_p = rl_sub.add_parser("list", help="List review labels for a campaign")
    rl_list_p.add_argument("--campaign-id", required=True, help="Campaign ID")
    rl_export_p = rl_sub.add_parser("export", help="Export all review labels as CSV")
    rl_export_p.add_argument("--output", default="review_labels.csv", help="Output CSV path")

    # Phase 8: label-completeness
    lc_p = sub.add_parser("label-completeness", help="Phase 8 review-label completeness tooling")
    lc_sub = lc_p.add_subparsers(dest="lc_command")
    lc_check_p = lc_sub.add_parser("check", help="Check label completeness for campaigns")
    lc_check_p.add_argument("--campaign-ids", nargs="+", required=True,
                             help="Campaign IDs to check (space-separated)")
    lc_export_p = lc_sub.add_parser("export-targets", help="Export label targets CSV")
    lc_export_p.add_argument("--campaign-ids", nargs="+", required=True,
                              help="Campaign IDs to check")
    lc_export_p.add_argument("--output", default="label_targets.csv", help="Output CSV path")

    # Phase 8: baseline (extended)
    baseline_p.add_argument("--name", default="", help="Baseline name (for show command)")
    baseline_sub.add_parser("list", help="List all known frozen baselines")
    baseline_show_p = baseline_sub.add_parser("show", help="Show a specific baseline")
    baseline_show_p.add_argument("baseline_id", help="Baseline ID (e.g. phase5_validated, phase7d_reviewed)")
    baseline_compare_reviewed_p = baseline_sub.add_parser(
        "compare-reviewed", help="Compare a batch to the Phase 7D reviewed baseline"
    )
    baseline_compare_reviewed_p.add_argument("--batch", required=True, help="Batch summary JSON path")
    baseline_compare_reviewed_p.add_argument("--baseline", default="phase7d_reviewed",
                                             help="Baseline ID (default: phase7d_reviewed)")
    # Phase 8B: freeze a new reviewed baseline
    baseline_freeze_p = baseline_sub.add_parser(
        "freeze", help="Freeze a reviewed batch as a new trusted baseline"
    )
    baseline_freeze_p.add_argument("--name", required=True,
                                   help="Baseline name (e.g. phase8_reviewed)")
    baseline_freeze_p.add_argument("--batch-id", required=True,
                                   help="Batch ID (e.g. phase8_batch_20260309)")
    baseline_freeze_p.add_argument("--batch-dir", default="",
                                   help="Batch artifact directory (default: runtime/evaluation_batches/<batch-id>)")
    baseline_freeze_p.add_argument("--note", default="", help="Note to attach to frozen baseline")

    # Phase 8B: challenger-trial
    ct_p = sub.add_parser("challenger-trial", help="Phase 8B bounded challenger-vs-champion trial")
    ct_sub = ct_p.add_subparsers(dest="ct_command")
    ct_show_p = ct_sub.add_parser("show", help="Show a challenger trial summary")
    ct_show_p.add_argument("trial_dir", help="Path to trial directory")
    ct_build_p = ct_sub.add_parser("build", help="Build trial summary from campaign IDs")
    ct_build_p.add_argument("--champion-campaigns", nargs="+", required=True,
                            help="Champion arm campaign IDs")
    ct_build_p.add_argument("--challenger-campaigns", nargs="+", required=True,
                            help="Challenger arm campaign IDs")
    ct_build_p.add_argument("--challenger-id", required=True, help="Challenger policy ID")
    ct_build_p.add_argument("--output-dir", required=True, help="Directory to write trial artifacts")
    ct_build_p.add_argument("--profile", default="eval_clean_energy_30m", help="Profile used")
    ct_build_p.add_argument("--baseline", default="phase8_reviewed",
                            help="Reviewed baseline ID for regression guard")

    # Phase 8: daily
    daily_p = sub.add_parser("daily", help="Phase 8 bounded daily automation")
    daily_sub = daily_p.add_subparsers(dest="daily_command")
    daily_run_p = daily_sub.add_parser("run", help="Run a daily automation profile")
    daily_run_p.add_argument("profile_name", help="Profile name (e.g. evaluation_daily_clean_energy)")
    daily_run_p.add_argument("--force", action="store_true", help="Skip max-runs-per-day guard (for batch collection)")
    daily_dryrun_p = daily_sub.add_parser("dry-run", help="Dry run a daily automation profile")
    daily_dryrun_p.add_argument("profile_name", help="Profile name")
    daily_sub.add_parser("status", help="Show status of today's daily automation runs")
    daily_sub.add_parser("list-profiles", help="List available daily automation profiles")

    # Phase 8: review-queue
    rq_p = sub.add_parser("review-queue", help="Phase 8 review queue commands")
    rq_sub = rq_p.add_subparsers(dest="rq_command")
    rq_list_p = rq_sub.add_parser("list", help="List review queue items")
    rq_list_p.add_argument("--status", default="pending",
                           choices=["pending", "reviewed", "all"], help="Filter by status")
    rq_inspect_p = rq_sub.add_parser("inspect", help="Inspect a review queue item")
    rq_inspect_p.add_argument("item_id", help="Review queue item ID")
    rq_mark_p = rq_sub.add_parser("mark-reviewed", help="Mark a review queue item as reviewed")
    rq_mark_p.add_argument("item_id", help="Review queue item ID")
    rq_mark_p.add_argument("--reviewer", default="operator", help="Reviewer identifier")

    # PV domain loop
    pv_p = sub.add_parser("pv", help="PV I-V characterization optimization loop")
    pv_sub = pv_p.add_subparsers(dest="pv_command")
    pv_run_p = pv_sub.add_parser("run", help="Run one PV optimization loop iteration")
    pv_run_p.add_argument("--candidates", type=int, default=6, help="Number of candidates to generate")
    pv_run_p.add_argument("--threshold", type=float, default=0.55, help="Promotion score threshold")
    pv_run_p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    pv_sub.add_parser("status", help="Show PV loop history and memory")
    pv_sub.add_parser("memory", help="Show accumulated PV idea and experiment memory")
    pv_dry_p = pv_sub.add_parser("dry-run", help="Preview PV candidates without running experiments")
    pv_dry_p.add_argument("--candidates", type=int, default=6, help="Number of candidates")
    pv_dry_p.add_argument("--seed", type=int, default=None, help="Random seed")
    pv_bench_p = pv_sub.add_parser("benchmark", help="Run PV benchmark with held-out realism check")
    pv_bench_p.add_argument("--candidates", type=int, default=6, help="Number of candidates")
    pv_bench_p.add_argument("--threshold", type=float, default=0.55, help="Promotion threshold")
    pv_bench_p.add_argument("--seed", type=int, default=42, help="Random seed (default: 42 for reproducibility")

    # Battery domain loop
    bat_p = sub.add_parser("battery", help="Battery ECM + cycle characterization optimization loop")
    bat_sub = bat_p.add_subparsers(dest="battery_command")
    bat_run_p = bat_sub.add_parser("run", help="Run one battery optimization loop iteration")
    bat_run_p.add_argument("--candidates", type=int, default=6, help="Number of candidates to generate")
    bat_run_p.add_argument("--threshold", type=float, default=0.84, help="Promotion score threshold")
    bat_run_p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    bat_run_p.add_argument("--no-sidecar", action="store_true", help="Disable PyBaMM sidecar verification")
    bat_run_p.add_argument("--mock-sidecar", action="store_true", help="Use mock sidecar for deterministic testing")
    bat_sub.add_parser("status", help="Show battery loop history and memory")
    bat_sub.add_parser("memory", help="Show accumulated battery idea and experiment memory")
    bat_dry_p = bat_sub.add_parser("dry-run", help="Preview battery candidates without running experiments")
    bat_dry_p.add_argument("--candidates", type=int, default=6, help="Number of candidates")
    bat_dry_p.add_argument("--seed", type=int, default=None, help="Random seed")
    bat_bench_p = bat_sub.add_parser("benchmark", help="Run battery benchmark with held-out realism check")
    bat_bench_p.add_argument("--candidates", type=int, default=6, help="Number of candidates")
    bat_bench_p.add_argument("--threshold", type=float, default=0.84, help="Promotion threshold")
    bat_bench_p.add_argument("--seed", type=int, default=42, help="Random seed (default: 42 for reproducibility)")
    bat_bench_p.add_argument("--no-sidecar", action="store_true", help="Disable PyBaMM sidecar verification")
    bat_bench_p.add_argument("--mock-sidecar", action="store_true", help="Use mock sidecar for deterministic testing")
    # Battery review workflow
    bat_sub.add_parser("briefs", help="List battery decision briefs")
    bat_inspect_p = bat_sub.add_parser("inspect", help="Inspect a battery decision brief")
    bat_inspect_p.add_argument("brief_id", help="Brief ID to inspect")
    bat_review_p = bat_sub.add_parser("review", help="Set review state on a brief")
    bat_review_p.add_argument("brief_id", help="Brief ID to review")
    bat_review_p.add_argument("--state", required=True,
                              choices=["approved_for_validation", "rejected_by_operator",
                                       "needs_more_analysis", "exported"],
                              help="Review state to set")
    bat_review_p.add_argument("--reviewer", default="", help="Reviewer name")
    bat_review_p.add_argument("--notes", default="", help="Review notes")
    bat_export_p = bat_sub.add_parser("export", help="Export a brief for external use")
    bat_export_p.add_argument("brief_id", help="Brief ID to export")

    # Phase 10A: KG shadow foundation
    ingest_p = sub.add_parser("ingest", help="Phase 10A paper ingestion into KG staging")
    ingest_sub = ingest_p.add_subparsers(dest="ingest_command")
    ingest_run_p = ingest_sub.add_parser("run", help="Ingest papers into bt_paper_segments")
    ingest_run_p.add_argument("--domain", default="clean-energy", help="Domain to ingest for")
    ingest_run_p.add_argument("--limit", type=int, default=100, help="Max papers to ingest")
    ingest_run_p.add_argument("--source", default="findings", choices=["findings", "evidence"],
                              help="Ingestion source")
    ingest_run_p.add_argument("--compress", action="store_true", help="Compress segments via Ollama")
    ingest_status_p = ingest_sub.add_parser("status", help="Show ingestion status")
    ingest_status_p.add_argument("--domain", default="", help="Filter by domain")

    kg_p = sub.add_parser("kg", help="Phase 10A knowledge graph commands")
    kg_sub = kg_p.add_subparsers(dest="kg_command")
    kg_extract_p = kg_sub.add_parser("extract", help="Extract entities/relations from segments")
    kg_extract_p.add_argument("--domain", default="", help="Domain to extract for")
    kg_extract_p.add_argument("--limit", type=int, default=50, help="Max segments to process")
    kg_extract_p.add_argument("--mock", action="store_true", help="Use mock extractor (no LLM)")
    kg_sub.add_parser("stats", help="Show KG entity/relation counts")
    kg_compare_p = kg_sub.add_parser("compare", help="Compare current vs KG shadow retrieval")
    kg_compare_p.add_argument("--domain", default="clean-energy", help="Domain to compare")
    kg_compare_p.add_argument("--limit", type=int, default=20, help="Evidence limit per source")
    kg_compare_p.add_argument("--output-dir", default="runtime/kg_comparisons",
                              help="Output directory for comparison artifacts")
    kg_writeback_p = kg_sub.add_parser("writeback-status", help="Show KG write-back findings")
    kg_writeback_p.add_argument("--domain", default="", help="Filter by domain")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    if not args.command:
        parser.print_help()
        return

    if args.command == "doctor":
        _cmd_doctor(args)
        return

    if args.command == "preflight":
        _cmd_preflight(args)
        return

    if args.command == "benchmark":
        _cmd_benchmark(args)
        return

    if args.command == "schedule":
        _cmd_schedule(args)
        return

    if args.command == "omniverse":
        _cmd_omniverse(args)
        return

    db = init_db(db_path=args.db)
    repo = Repository(db)

    if args.command == "run":
        _cmd_run(repo, args)
    elif args.command == "list-publications":
        _cmd_list_publications(repo)
    elif args.command == "show-run":
        _cmd_show_run(repo, args)
    elif args.command == "list-runs":
        _cmd_list_runs(repo)
    elif args.command == "validate-config":
        _cmd_validate_config(args)
    elif args.command == "list-programs":
        _cmd_list_programs()
    elif args.command == "serve":
        _cmd_serve(args)
    elif args.command == "review":
        _cmd_review(repo, args)
    elif args.command == "metrics":
        _cmd_metrics(repo, args)
    elif args.command == "baseline":
        _cmd_baseline(repo, args)
    elif args.command == "policy":
        _cmd_policy(repo, args)
    elif args.command == "daily-search":
        _cmd_daily_search(repo, args)
    elif args.command == "cockpit":
        _cmd_cockpit(repo, args)
    elif args.command == "falsify":
        _cmd_falsify(repo, args)
    elif args.command == "campaign":
        _cmd_campaign(repo, args)
    elif args.command == "evaluation-pack":
        _cmd_evaluation_pack(args)
    elif args.command == "review-label":
        _cmd_review_label(repo, args)
    elif args.command == "label-completeness":
        _cmd_label_completeness(repo, args)
    elif args.command == "daily":
        _cmd_daily(repo, args)
    elif args.command == "review-queue":
        _cmd_review_queue(repo, args)
    elif args.command == "challenger-trial":
        _cmd_challenger_trial(repo, args)
    elif args.command == "pv":
        _cmd_pv(repo, args)
    elif args.command == "battery":
        _cmd_battery(repo, args)
    elif args.command == "ingest":
        _cmd_ingest(repo, args)
    elif args.command == "kg":
        _cmd_kg(repo, args)


def _cmd_run(repo: Repository, args):
    try:
        program = load_program(args.program)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Override mode if specified
    if args.mode:
        from .models import RunMode
        try:
            program.mode = RunMode(args.mode)
        except ValueError:
            print(f"Error: Invalid mode '{args.mode}'. Valid: {[m.value for m in RunMode]}", file=sys.stderr)
            sys.exit(1)

    errors = validate_program(program)
    if errors:
        print("Config validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    print(f"Starting breakthrough cycle for program: {program.name}")
    print(f"  Domain: {program.domain}")
    print(f"  Mode: {program.mode.value}")
    print(f"  Candidate budget: {program.candidate_budget}")
    print()

    orchestrator = BreakthroughOrchestrator(program=program, repo=repo)
    run_record = orchestrator.run()

    # Save reports
    json_path, md_path = save_reports(repo, run_record.id)

    print()
    print(f"Run completed: {run_record.status.value}")
    print(f"  Run ID: {run_record.id}")
    print(f"  Candidates generated: {run_record.candidates_generated}")
    print(f"  Candidates rejected: {run_record.candidates_rejected}")

    if run_record.publication_id:
        pub = repo.get_publication(run_record.publication_id)
        if pub:
            print(f"\n  PUBLISHED: {pub['candidate_title']}")
            print(f"  Status: {pub['status_label']}")
    else:
        # Check for draft
        draft = repo.get_draft_by_run(run_record.id)
        if draft:
            print(f"\n  DRAFT PENDING REVIEW: {draft['candidate_title']}")
            print(f"  Draft ID: {draft['id']}")
            print(f"  Use 'review approve {draft['id']}' to publish")
        else:
            print("\n  No candidate met the publication threshold.")

    print(f"\n  JSON report: {json_path}")
    print(f"  Markdown report: {md_path}")

    # Print markdown report to stdout
    print("\n" + "=" * 60)
    md = generate_markdown_report(repo, run_record.id)
    print(md)


def _cmd_list_publications(repo: Repository):
    pubs = repo.list_publications(limit=20)
    if not pubs:
        print("No publications yet.")
        return
    for pub in pubs:
        print(f"  [{pub['id'][:12]}] {pub['candidate_title']} ({pub['publication_date']}) - {pub['status_label']}")


def _cmd_show_run(repo: Repository, args):
    md = generate_markdown_report(repo, args.run_id)
    print(md)


def _cmd_list_runs(repo: Repository):
    runs = repo.list_runs(limit=20)
    if not runs:
        print("No runs yet.")
        return
    for r in runs:
        print(f"  [{r['id'][:12]}] {r['program_name']} - {r['status']} ({r['started_at']})")


def _cmd_validate_config(args):
    try:
        program = load_program(args.name)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    errors = validate_program(program)
    if errors:
        print("Validation FAILED:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print(f"Config '{args.name}' is valid.")
        print(f"  Domain: {program.domain}")
        print(f"  Mode: {program.mode.value}")
        print(f"  Candidate budget: {program.candidate_budget}")
        print(f"  Publication threshold: {program.publication_threshold}")


def _cmd_list_programs():
    programs = list_programs()
    if not programs:
        print("No research programs found in config/research_programs/")
        return
    for name in programs:
        print(f"  {name}")


def _cmd_serve(args):
    from flask import Flask
    from .api import bp, configure

    configure(db_path=None)
    app = Flask(__name__)
    app.register_blueprint(bp)
    print(f"Starting Breakthrough Engine API on port {args.port}")
    app.run(host="127.0.0.1", port=args.port, debug=False)


def _cmd_benchmark(args):
    if not hasattr(args, "bench_command") or args.bench_command != "run":
        print("Usage: python -m breakthrough_engine benchmark run")
        return

    from .benchmark import run_benchmark_suite
    print("Running benchmark suite...")
    print()
    suite = run_benchmark_suite()
    print(suite.summary())
    print()

    if suite.failed > 0:
        sys.exit(1)


def _cmd_schedule(args):
    if not hasattr(args, "sched_command") or not args.sched_command:
        print("Usage: python -m breakthrough_engine schedule {run-once|generate-plist}")
        return

    if args.sched_command == "run-once":
        from .scheduler import run_scheduled
        program_name = args.program if hasattr(args, "program") else "general_fast_loop"
        print(f"Executing scheduled run for program: {program_name}")
        status, message = run_scheduled(program_name=program_name)
        print(f"Status: {status.value}")
        print(f"Message: {message}")
        if status.value == "failed":
            sys.exit(1)

    elif args.sched_command == "generate-plist":
        from .scheduler import generate_launchd_plist
        program_name = args.program if hasattr(args, "program") else "general_fast_loop"
        hour = args.hour if hasattr(args, "hour") else 6
        minute = args.minute if hasattr(args, "minute") else 0
        plist = generate_launchd_plist(program_name=program_name, hour=hour, minute=minute)
        print(plist)


def _cmd_omniverse(args):
    if not hasattr(args, "omni_command") or not args.omni_command:
        print("Usage: python -m breakthrough_engine omniverse {build-bundle|ingest-result}")
        return

    if args.omni_command == "build-bundle":
        from .simulator import OmniverseSimulatorAdapter
        from .models import SimulationSpec

        db = init_db(db_path=getattr(args, "db", None))
        repo = Repository(db)

        candidate = repo.get_candidate(args.candidate_id)
        if not candidate:
            print(f"Error: Candidate {args.candidate_id} not found", file=sys.stderr)
            sys.exit(1)

        spec = SimulationSpec(
            candidate_id=args.candidate_id,
            simulator="omniverse",
            objective=f"Validate: {candidate.get('expected_outcome', 'N/A')[:100]}",
            parameters={"hypothesis_hash": hash(candidate.get("statement", "")) % 10000},
        )

        adapter = OmniverseSimulatorAdapter(dry_run=True)
        errors = adapter.validate_config(spec)
        if errors:
            print("Validation errors:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)

        bundle_path = adapter.build_bundle(spec)
        print(f"Bundle created: {bundle_path}")
        print(f"  spec.json: {bundle_path / 'spec.json'}")
        print(f"  config.json: {bundle_path / 'config.json'}")
        print(f"  README.md: {bundle_path / 'README.md'}")
        print(f"  results/: ready for result ingestion")

    elif args.omni_command == "ingest-result":
        from .simulator import OmniverseSimulatorAdapter

        try:
            result = OmniverseSimulatorAdapter.ingest_result(args.path)
            print(f"Result ingested successfully:")
            print(f"  Candidate ID: {result.candidate_id}")
            print(f"  Status: {result.status.value}")
            print(f"  Metrics: {json.dumps(result.key_metrics, indent=2)}")
            print(f"  Summary: {result.pass_fail_summary}")

            # Save to DB
            db = init_db(db_path=getattr(args, "db", None))
            repo = Repository(db)
            repo.save_simulation_result(result)
            print(f"  Saved to database as result {result.id}")

        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def _cmd_review(repo: Repository, args):
    if not hasattr(args, "review_command") or not args.review_command:
        print("Usage: python -m breakthrough_engine review {list|show|approve|reject}")
        return

    if args.review_command == "list":
        drafts = repo.list_drafts(status="pending_review")
        if not drafts:
            print("No drafts pending review.")
            return
        print("Drafts pending review:")
        for d in drafts:
            print(f"  [{d['id'][:12]}] {d['candidate_title']} (run={d['run_id'][:8]}) status={d['status']}")

    elif args.review_command == "show":
        draft = repo.get_draft(args.draft_id)
        if not draft:
            print(f"Draft {args.draft_id} not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Draft: {draft['id']}")
        print(f"  Title: {draft['candidate_title']}")
        print(f"  Run: {draft['run_id']}")
        print(f"  Status: {draft['status']}")
        print(f"  Hypothesis: {draft['hypothesis'][:200]}")
        print(f"  Evidence: {draft.get('evidence_summary', 'N/A')[:200]}")
        print(f"  Novelty: {draft.get('novelty_summary', 'N/A')[:200]}")
        print(f"  Replication Priority: {draft.get('replication_priority', 'N/A')}")

    elif args.review_command == "approve":
        from .review import approve_draft
        notes = args.notes if hasattr(args, "notes") else ""
        pub = approve_draft(repo, args.draft_id, reviewer="cli_operator", notes=notes)
        if pub:
            print(f"Draft approved. Publication created: {pub.id}")
        else:
            print("Failed to approve draft (not found or already reviewed).", file=sys.stderr)
            sys.exit(1)

    elif args.review_command == "reject":
        from .review import reject_draft
        reason = args.reason if hasattr(args, "reason") else ""
        ok = reject_draft(repo, args.draft_id, reviewer="cli_operator", reason=reason)
        if ok:
            print(f"Draft rejected.")
        else:
            print("Failed to reject draft (not found or already reviewed).", file=sys.stderr)
            sys.exit(1)


def _cmd_doctor(args):
    """Check system readiness: Ollama connectivity, model availability, DB, findings."""
    import os
    import sqlite3

    checks = []

    # 1. Ollama connectivity
    try:
        import requests
        host = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
        resp = requests.get(f"http://{host}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        model_names = [m["name"] for m in models]
        checks.append(("Ollama server", "PASS", f"Reachable at {host}, {len(models)} model(s)"))

        # 2. Required model
        target_model = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")
        if any(target_model in n for n in model_names):
            checks.append(("Model available", "PASS", f"{target_model} found"))
        else:
            checks.append(("Model available", "FAIL", f"{target_model} not found. Available: {', '.join(model_names)}"))
    except Exception as e:
        checks.append(("Ollama server", "FAIL", f"Not reachable: {e}"))
        checks.append(("Model available", "FAIL", "Cannot check (server unreachable)"))

    # 3. Database
    db_path = getattr(args, "db", None) or os.path.join(
        os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "db", "scires.db"
    )
    if os.path.exists(db_path):
        checks.append(("Database file", "PASS", f"Exists at {db_path}"))
        try:
            db = sqlite3.connect(db_path)
            # Check bt_ tables
            tables = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bt_%'"
            ).fetchall()]
            checks.append(("BT tables", "PASS" if tables else "WARN", f"{len(tables)} bt_ tables"))

            # Check findings table
            try:
                count = db.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
                checks.append(("Findings table", "PASS" if count > 0 else "WARN",
                              f"{count} findings"))
            except sqlite3.OperationalError:
                checks.append(("Findings table", "FAIL", "Table does not exist"))

            # Check papers table
            try:
                count = db.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
                checks.append(("Papers table", "PASS" if count > 0 else "WARN",
                              f"{count} papers"))
            except sqlite3.OperationalError:
                checks.append(("Papers table", "FAIL", "Table does not exist"))

            db.close()
        except Exception as e:
            checks.append(("Database read", "FAIL", str(e)))
    else:
        checks.append(("Database file", "WARN", f"Not found at {db_path} (will be created on first run)"))

    # 4. Research programs
    from .config_loader import list_programs
    programs = list_programs()
    checks.append(("Research programs", "PASS" if programs else "FAIL",
                   f"{len(programs)} programs: {', '.join(programs)}"))

    # Print results
    print("Breakthrough Engine - System Readiness Check")
    print("=" * 55)
    all_pass = True
    for name, status, detail in checks:
        icon = {"PASS": "+", "FAIL": "X", "WARN": "!"}[status]
        print(f"  [{icon}] {name}: {status} — {detail}")
        if status == "FAIL":
            all_pass = False
    print("=" * 55)

    if all_pass:
        print("All checks passed. System is ready for production runs.")
    else:
        print("Some checks failed. Address the issues above before running production modes.")
        sys.exit(1)


def _cmd_metrics(repo: Repository, args):
    if not hasattr(args, "metrics_command") or not args.metrics_command:
        print("Usage: python -m breakthrough_engine metrics recent")
        return

    if args.metrics_command == "recent":
        metrics_list = repo.list_recent_metrics(limit=10)
        if not metrics_list:
            print("No run metrics available.")
            return
        print("Recent run metrics:")
        for m in metrics_list:
            print(f"  Run {m['run_id'][:12]}: duration={m['total_duration_seconds']:.1f}s "
                  f"evidence={m['evidence_count']} "
                  f"novelty_fail={m['novelty_fail_count']} "
                  f"draft={bool(m['draft_created'])} "
                  f"pub={bool(m['publication_created'])}")


# ---------------------------------------------------------------------------
# Phase 6 CLI handlers
# ---------------------------------------------------------------------------

def _cmd_baseline(repo: Repository, args):
    if not hasattr(args, "baseline_command") or not args.baseline_command:
        print("Usage: python -m breakthrough_engine baseline [compare|list|show|compare-reviewed]")
        return
    if args.baseline_command == "compare":
        from .baseline_comparator import BaselineComparator, BenchmarkConfig
        print("Running Phase 5 baseline comparison (offline-safe, DETERMINISTIC_TEST mode)...")
        comp = BaselineComparator()
        try:
            baseline = comp.load_phase5_baseline()
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        config = BenchmarkConfig()
        current = comp.run_benchmark(config, repo)
        report = comp.compare(baseline, current)
        print(comp.format_report(report))
        comp.save_comparison(repo, report)
        if report.has_regression:
            print("\nWARNING: Regression detected vs Phase 5 baseline.")
            sys.exit(1)
        else:
            print("\nNo regressions. System is at or above Phase 5 baseline.")
    elif args.baseline_command == "list":
        from .reviewed_baseline import get_registry
        reg = get_registry()
        baselines = reg.list_baselines()
        print(f"{'ID':<25} {'Type':<25} {'Exists':<8} {'Frozen At':<25} {'Campaigns'}")
        print("-" * 90)
        for b in baselines:
            exists = "YES" if b["exists"] else "NO"
            frozen = b.get("frozen_at", "")[:10]
            campaigns = b.get("campaign_count", "?")
            btype = b.get("baseline_type", "")
            print(f"{b['baseline_id']:<25} {btype:<25} {exists:<8} {frozen:<25} {campaigns}")
    elif args.baseline_command == "show":
        from .reviewed_baseline import get_registry
        import json
        baseline_id = args.baseline_id
        reg = get_registry()
        b = reg.load(baseline_id)
        if b is None:
            print(f"Baseline not found: {baseline_id}", file=sys.stderr)
            sys.exit(1)
        print(f"Baseline: {b.baseline_name}")
        print(f"  ID: {b.baseline_id}")
        print(f"  Type: {b.baseline_type}")
        print(f"  Frozen at: {b.frozen_at}")
        print(f"  Branch: {b.branch}")
        print(f"  Commit: {b.commit}")
        print(f"  Profile: {b.profile}")
        print(f"  Domain: {b.domain}")
        print(f"  Campaigns: {b.campaign_count}")
        if b.summary_statistics:
            print(f"  Summary statistics:")
            for k, v in b.summary_statistics.items():
                if isinstance(v, float):
                    print(f"    {k}: {v:.4f}")
                else:
                    print(f"    {k}: {v}")
        print(f"  Note: {b.note}")
    elif args.baseline_command == "compare-reviewed":
        import json
        from .reviewed_baseline import get_registry
        batch_path = args.batch
        baseline_id = args.baseline
        if not os.path.exists(batch_path):
            print(f"Batch summary not found: {batch_path}", file=sys.stderr)
            sys.exit(1)
        with open(batch_path) as f:
            batch_summary = json.load(f)
        reg = get_registry()
        result = reg.compare_batch_to_reviewed_baseline(batch_summary, baseline_id)
        if "error" in result:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"Reviewed Baseline Comparison: {baseline_id}")
        print(f"  Baseline campaigns: {result['baseline_campaign_count']}")
        print(f"  Current campaigns: {result['current_campaign_count']}")
        print()
        print(f"{'Metric':<35} {'Baseline':<12} {'Current':<12} {'Delta':<10} {'Status'}")
        print("-" * 85)
        for c in result["comparisons"]:
            status = "✓ OK" if c["status"] == "OK" else "✗ REGRESSION"
            delta = f"{c['delta']:+.4f}" if c["delta"] is not None else "N/A"
            print(f"{c['metric']:<35} {str(c.get('baseline', 'N/A')):<12} {str(c.get('current', 'N/A')):<12} {delta:<10} {status}")
        print()
        if result["regression_found"]:
            print("REGRESSION FOUND vs Phase 7D reviewed baseline.")
            sys.exit(1)
        else:
            print("No regressions vs Phase 7D reviewed baseline.")

    elif args.baseline_command == "freeze":
        import json as _json
        from datetime import datetime, timezone

        batch_id = args.batch_id
        batch_dir = args.batch_dir or os.path.join("runtime", "evaluation_batches", batch_id)
        batch_json_path = os.path.join(batch_dir, "batch_summary.json")

        if not os.path.exists(batch_json_path):
            print(f"Error: batch_summary.json not found at {batch_json_path}", file=sys.stderr)
            sys.exit(1)

        with open(batch_json_path) as f:
            batch = _json.load(f)

        stats = batch.get("summary_statistics", {})
        campaigns = batch.get("campaigns", [])

        # Build baseline artifact
        baseline_name = args.name
        baseline_id = baseline_name.replace(" ", "_").lower()
        frozen_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Determine branch and commit from git
        try:
            import subprocess
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"], text=True
            ).strip()
            commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], text=True
            ).strip()
        except Exception:
            branch = ""
            commit = ""

        summary_stats = {
            "champion_score_mean": stats.get("champion_score_mean"),
            "champion_score_min": stats.get("champion_score_min"),
            "champion_score_max": stats.get("champion_score_max"),
            "integrity_ok_rate": stats.get("integrity_ok_rate", 1.0),
            "falsification_complete_rate": stats.get("falsification_complete_rate", 1.0),
            "overall_block_rate": stats.get("overall_block_rate"),
            "total_candidates_generated": stats.get("total_candidates_generated"),
            "total_finalists": stats.get("total_finalists"),
        }
        note_text = args.note or f"Frozen from batch {batch_id} on {frozen_at[:10]}"
        campaign_id_list = [c.get("campaign_id", "") for c in campaigns]
        campaign_count = batch.get("campaign_count", len(campaigns))

        # Write JSON using keys compatible with ReviewedBaseline.from_dict()
        runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        out_path = os.path.join(runtime_root, "baselines", f"{baseline_id}_baseline.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        baseline_dict = {
            "baseline_id": baseline_id,
            "baseline_name": baseline_name,
            "baseline_type": "reviewed_batch",
            "frozen_at": frozen_at,
            "branch": branch,
            "commit": commit,
            "commit_hash": commit,
            "profile": batch.get("profile", ""),
            "domain": "clean-energy",
            "schema_version": batch.get("schema_version", "v003"),
            "generation_model": "",
            "embedding_model": "",
            "champion_policy": batch.get("policy_used", "phase5_champion"),
            "batch_id": batch_id,
            "campaign_ids": campaign_id_list,
            "campaign_count": campaign_count,
            "all_integrity_ok": batch.get("all_integrity_ok", True),
            "all_falsification_complete": batch.get("all_falsification_complete", True),
            "summary_statistics": summary_stats,
            "regression_thresholds": {
                "champion_score_mean_regression": -0.05,
                "integrity_ok_rate_min": 1.0,
                "falsification_complete_rate_min": 1.0,
                "block_rate_max_regression": 0.10,
            },
            "review_label_status": {},
            "best_champion": batch.get("best_champion", {}),
            "weakest_champion": batch.get("weakest_champion", {}),
            "note": note_text,
            "is_read_only": True,
        }

        with open(out_path, "w") as f:
            _json.dump(baseline_dict, f, indent=2)

        print(f"Frozen baseline: {baseline_id}")
        print(f"  File: {out_path}")
        print(f"  Campaigns: {campaign_count}")
        print(f"  Champion score mean: {stats.get('champion_score_mean', 'N/A')}")
        print(f"  Integrity OK rate: {stats.get('integrity_ok_rate', 'N/A')}")
        print(f"  Branch: {branch}  Commit: {commit}")
        print(f"  Note: {note_text}")


def _cmd_policy(repo: Repository, args):
    if not hasattr(args, "policy_command") or not args.policy_command:
        print("Usage: python -m breakthrough_engine policy [list|show|promote|manual-promote|rollback|register]")
        return
    from .policy_registry import PolicyRegistry
    registry = PolicyRegistry(repo)

    if args.policy_command == "list":
        champion = registry.get_champion()
        challengers = registry.get_challengers()
        probations = registry.get_probation_policies()
        print(f"Champion: {champion.name} (id={champion.id}) version={champion.version}")
        if probations:
            print(f"Probation ({len(probations)}):")
            for p in probations:
                print(f"  {p.name} (id={p.id})")
        if challengers:
            print(f"Challengers ({len(challengers)}):")
            for c in challengers:
                print(f"  {c.name} (id={c.id})")
        else:
            print("No challengers registered.")

    elif args.policy_command == "show":
        all_policies = registry.list_all()
        pol = next((p for p in all_policies if p.id == args.policy_id), None)
        if not pol:
            print(f"Policy not found: {args.policy_id}", file=sys.stderr)
            sys.exit(1)
        import json
        print(f"Policy: {pol.name} (id={pol.id})")
        print(f"  Version: {pol.version}")
        print(f"  generation_prompt_variant: {pol.generation_prompt_variant}")
        print(f"  diversity_steering_variant: {pol.diversity_steering_variant}")
        print(f"  negative_memory_strategy: {pol.negative_memory_strategy}")
        history = registry.get_trial_history(policy_id=args.policy_id)
        print(f"  Trials: {len(history)}")
        for t in history[-5:]:
            print(f"    [{t.trial_type}] {t.outcome}")

    elif args.policy_command == "promote":
        ok, reason_msg = registry.promote_to_probation(args.policy_id, evidence={"reason": args.reason})
        if ok:
            print(f"Policy {args.policy_id} promoted to probation.")
        else:
            print(f"Promotion failed: {reason_msg}")
            sys.exit(1)

    elif args.policy_command == "manual-promote":
        # Manual promotion: bypass trial count, promote directly to champion.
        # Used after an external A/B trial with a documented PROMOTION_RECOMMENDED verdict.
        import json as _json
        from .policy_registry import PolicyConfig

        reason = args.reason
        policy_id = args.policy_id
        trial_id = getattr(args, "trial_id", "")

        # Auto-register from config file if not in DB
        policy = registry.get_policy(policy_id)
        if policy is None:
            config_path = os.path.join("config", "policies", f"{policy_id}.json")
            if os.path.exists(config_path):
                with open(config_path) as _f:
                    file_config = _json.load(_f)
                pc = PolicyConfig.from_dict({**file_config, "id": policy_id})
                registry.register(pc)
                print(f"Auto-registered {policy_id!r} from {config_path}")
            else:
                print(f"Error: policy {policy_id!r} not found in DB or config/policies/", file=sys.stderr)
                sys.exit(1)

        # Guard: already champion
        status = registry.get_policy_status(policy_id)
        if status == "champion":
            print(f"Policy {policy_id} is already champion — nothing to do.")
            return

        # Step 1: set probation flag (bypass trial_count gate — evidence is external A/B trial)
        repo.db.execute("UPDATE bt_policies SET is_probation=1 WHERE id=?", (policy_id,))
        repo.db.commit()

        # Step 2: promote from probation to champion
        evidence = {"manual_promotion": True, "trial_id": trial_id, "reason": reason}
        ok, msg = registry.promote_to_champion_reviewed(
            policy_id,
            evidence=evidence,
            reason=reason,
        )
        if ok:
            champion = registry.get_champion()
            print(f"Policy {policy_id!r} manually promoted to champion.")
            print(f"  Reason : {reason}")
            if trial_id:
                print(f"  Trial ID: {trial_id}")
            print(f"  Champion: {champion.name} (id={champion.id})")
        else:
            print(f"Manual promotion failed: {msg}", file=sys.stderr)
            sys.exit(1)

    elif args.policy_command == "rollback":
        ok, reason_msg = registry.rollback_champion(reason=args.reason or "operator rollback")
        if ok:
            print(f"Champion rolled back to previous. {reason_msg}")
        else:
            print(f"Rollback failed: {reason_msg}")
            sys.exit(1)

    elif args.policy_command == "register":
        import json as _json
        from .policy_registry import PolicyConfig, MAX_ACTIVE_CHALLENGERS

        # Enforce single-challenger limit for Phase 8B
        challengers = registry.get_challengers()
        if len(challengers) >= MAX_ACTIVE_CHALLENGERS:
            print(
                f"Error: max challengers ({MAX_ACTIVE_CHALLENGERS}) already registered. "
                "Rollback or remove an existing challenger before registering a new one.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Load from config file if provided
        scoring_weights = None
        gen_variant = getattr(args, "generation_prompt_variant", "standard")
        div_variant = getattr(args, "diversity_steering_variant", "standard")
        neg_strategy = getattr(args, "negative_memory_strategy", "standard")
        description = getattr(args, "description", "")

        config_path = getattr(args, "config_path", "")
        evidence_ranking_weights = None
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    file_config = _json.load(f)
                gen_variant = file_config.get("generation_prompt_variant", gen_variant)
                div_variant = file_config.get("diversity_steering_variant", div_variant)
                neg_strategy = file_config.get("negative_memory_strategy", neg_strategy)
                scoring_weights = file_config.get("scoring_weights")
                evidence_ranking_weights = file_config.get("evidence_ranking_weights")
                description = description or file_config.get("description", "")
            except Exception as e:
                print(f"Warning: could not read config file {config_path}: {e}", file=sys.stderr)

        scoring_weights_json = getattr(args, "scoring_weights_json", "")
        if scoring_weights_json:
            try:
                scoring_weights = _json.loads(scoring_weights_json)
            except Exception as e:
                print(f"Error: invalid --scoring-weights-json: {e}", file=sys.stderr)
                sys.exit(1)

        config = PolicyConfig(
            name=args.name,
            version="1.0",
            description=description,
            generation_prompt_variant=gen_variant,
            diversity_steering_variant=div_variant,
            negative_memory_strategy=neg_strategy,
            scoring_weights=scoring_weights,
            evidence_ranking_weights=evidence_ranking_weights,
        )
        registered = registry.register(config)
        print(f"Registered challenger: {registered.name} (id={registered.id})")
        print(f"  generation_prompt_variant: {registered.generation_prompt_variant}")
        print(f"  diversity_steering_variant: {registered.diversity_steering_variant}")
        print(f"  negative_memory_strategy: {registered.negative_memory_strategy}")
        if registered.scoring_weights:
            print(f"  scoring_weights: {registered.scoring_weights}")
        print(f"  Promotion: manual only (automatic promotion is OFF)")


def _cmd_daily_search(repo: Repository, args):
    if not hasattr(args, "ds_command") or not args.ds_command:
        print("Usage: python -m breakthrough_engine daily-search run [--mode MODE] [--budget MINUTES]")
        return
    if args.ds_command == "run":
        from .daily_search import DailySearchLadder, LadderConfig
        from .policy_registry import PolicyRegistry
        from .bayesian_evaluator import BayesianEvaluator
        from .falsification import FalsificationEngine
        from .config_loader import load_program

        mode = args.mode
        policy_id = getattr(args, "policy", None)

        config = LadderConfig(mode=mode)
        if mode == "production":
            config.production_wall_clock_budget_minutes = getattr(args, "budget", 30)
        if policy_id:
            config.policy_variants = [policy_id]

        try:
            program = load_program("benchmark_p6" if mode == "benchmark" else "daily_quality")
        except FileNotFoundError:
            program = load_program("general_fast_loop")

        registry = PolicyRegistry(repo)

        ladder = DailySearchLadder()
        print(f"Starting daily search campaign (mode={mode})...")
        result = ladder.run_campaign(repo, config, registry, program)

        print(f"\nCampaign {result.campaign_id[:12]}:")
        print(f"  Mode: {result.mode}")
        print(f"  Policy: {result.policy_used}")
        print(f"  Champion: {result.daily_champion_id or 'none'}")
        if result.daily_champion_title:
            print(f"  Title: {result.daily_champion_title}")
        print(f"  Rationale: {result.champion_selection_rationale}")
        print(f"  Candidates: {result.total_candidates_generated} generated, "
              f"{result.total_blocked} blocked, {result.total_shortlisted} shortlisted")
        print(f"  Elapsed: {result.elapsed_seconds:.1f}s")
        print(f"\nStages:")
        for stage in result.ladder_stages:
            print(f"  {stage.stage_name}: {stage.stop_reason} "
                  f"(trials={stage.trials_attempted}, advanced={stage.candidates_advanced}, "
                  f"best_score={stage.best_score:.3f})")


def _cmd_cockpit(repo: Repository, args):
    if not hasattr(args, "cockpit_command") or not args.cockpit_command:
        print("Usage: python -m breakthrough_engine cockpit show RUN_ID")
        return
    if args.cockpit_command == "show":
        from .review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        # Find best candidate from run
        rows = repo.db.execute(
            "SELECT id, title, statement, domain FROM bt_candidates WHERE run_id=? ORDER BY created_at DESC",
            (args.run_id,)
        ).fetchall()
        if not rows:
            print(f"No candidates found for run {args.run_id}", file=sys.stderr)
            sys.exit(1)
        # Find highest-scoring candidate
        best_row = None
        best_score = -1.0
        for row in rows:
            score_row = repo.get_score(row["id"])
            if score_row and score_row.get("final_score", 0) > best_score:
                best_score = score_row.get("final_score", 0)
                best_row = row
        if not best_row:
            best_row = rows[0]
            best_score = 0.0

        # Build minimal candidate object for packet
        from .models import CandidateHypothesis
        cand = CandidateHypothesis(
            id=best_row["id"], run_id=args.run_id,
            title=best_row["title"] or "", statement=best_row["statement"] or "",
            domain=best_row["domain"] or "",
        )
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, final_score=best_score,
        )
        print(cockpit.format_as_text(packet))


def _cmd_falsify(repo: Repository, args):
    from .falsification import FalsificationEngine
    falsifier = FalsificationEngine()
    row = repo.get_candidate(args.candidate_id)
    if not row:
        print(f"Candidate not found: {args.candidate_id}", file=sys.stderr)
        sys.exit(1)
    from .models import CandidateHypothesis
    cand = CandidateHypothesis(
        id=row["id"], run_id=row.get("run_id", ""),
        title=row.get("title", ""), statement=row.get("statement", ""),
        domain=row.get("domain", ""),
    )
    summary = falsifier.evaluate(cand, evidence_pack=None)
    print(f"Falsification result for {args.candidate_id[:12]}:")
    print(f"  Risk: {summary.overall_falsification_risk}")
    print(f"  Passed: {summary.falsification_passed}")
    print(f"  Reasoning: {summary.reasoning}")
    if summary.contradictions_found:
        print(f"  Contradictions: {summary.contradictions_found}")
    if summary.missing_evidence_gaps:
        print(f"  Missing evidence: {summary.missing_evidence_gaps}")
    if summary.bridge_weakness_flags:
        print(f"  Bridge weaknesses: {summary.bridge_weakness_flags}")
    falsifier.save_summary(repo, summary)
    print("Summary saved to database.")


# ---------------------------------------------------------------------------
# Phase 7A CLI handlers
# ---------------------------------------------------------------------------

def _cmd_preflight(args):
    """Run campaign preflight verification."""
    from .preflight import PreflightEngine
    engine = PreflightEngine()
    report = engine.run(
        db_path=getattr(args, "db", None),
        strict=getattr(args, "strict", False),
        campaign_profile=getattr(args, "profile", ""),
    )
    print(engine.format_report(report))
    if report.has_failures:
        sys.exit(1)


def _cmd_campaign(repo: Repository, args):
    """Manage autonomous campaigns."""
    if not hasattr(args, "campaign_command") or not args.campaign_command:
        print("Usage: python -m breakthrough_engine campaign [run|list|show|profiles]")
        return

    if args.campaign_command == "profiles":
        import os
        profiles_dir = "config/campaign_profiles"
        if not os.path.exists(profiles_dir):
            print("No campaign profiles directory found.")
            return
        profiles = [f.replace(".yaml", "") for f in os.listdir(profiles_dir) if f.endswith(".yaml")]
        print(f"Available campaign profiles ({len(profiles)}):")
        for p in sorted(profiles):
            print(f"  {p}")
        return

    if args.campaign_command == "run":
        from .campaign_manager import CampaignManager, load_campaign_profile
        profile_name = getattr(args, "profile", "pilot_30m")
        try:
            profile = load_campaign_profile(profile_name)
        except FileNotFoundError:
            print(f"Campaign profile not found: {profile_name}", file=sys.stderr)
            sys.exit(1)

        strict = getattr(args, "strict", True)
        dry_run = getattr(args, "dry_run", False)
        policy_id = getattr(args, "policy", None)

        # Resolve policy override for A/B trials (by ID or name)
        policy_override = None
        if policy_id:
            from .policy_registry import PolicyRegistry
            reg = PolicyRegistry(repo)
            policy_override = reg.get_policy(policy_id)
            if policy_override is None:
                # Try lookup by name
                rows = repo.db.execute(
                    "SELECT id FROM bt_policies WHERE name=?", (policy_id,)
                ).fetchall()
                if rows:
                    policy_override = reg.get_policy(rows[0][0] if not hasattr(rows[0], 'keys') else rows[0]["id"])
            if policy_override is None:
                print(f"Error: policy not found: {policy_id}", file=sys.stderr)
                sys.exit(1)

        manager = CampaignManager(repo=repo, db_path=getattr(args, "db", None))
        print(f"Launching campaign: {profile.profile_name} ({profile.profile_type})")
        if policy_id:
            print(f"  Policy override: {policy_id}")
        if dry_run:
            print("  (dry-run mode — preflight only)")

        receipt = manager.run_campaign(profile, strict_preflight=strict, dry_run=dry_run,
                                       policy_override=policy_override)

        print(f"\nCampaign {receipt.campaign_id[:12]}:")
        print(f"  Status: {receipt.status}")
        print(f"  Elapsed: {receipt.elapsed_seconds:.1f}s")
        if receipt.champion_candidate_id:
            print(f"  Champion: {receipt.champion_candidate_title or receipt.champion_candidate_id}")
        if receipt.failure_reason:
            print(f"  Failure: {receipt.failure_reason}")

        health = receipt.health_summary
        if health:
            print(f"  Healthy: {health.get('healthy', False)}")
            print(f"  Overnight ready: {health.get('overnight_ready', False)}")
            for issue in health.get("issues", []):
                print(f"    - {issue}")

        if receipt.artifact_paths:
            print(f"  Artifacts:")
            for p in receipt.artifact_paths:
                print(f"    {p}")

    elif args.campaign_command == "list":
        from .campaign_manager import CampaignManager
        manager = CampaignManager(repo=repo)
        campaigns = manager.list_campaigns(limit=getattr(args, "limit", 20))
        if not campaigns:
            print("No campaigns found.")
            return
        print(f"Recent campaigns ({len(campaigns)}):")
        for c in campaigns:
            print(
                f"  {c['campaign_id'][:12]}  {c['profile_name']:20s}  "
                f"{c['status']:25s}  {c.get('started_at', '')}"
            )

    elif args.campaign_command == "show":
        from .campaign_manager import CampaignManager
        manager = CampaignManager(repo=repo)
        receipt = manager.get_receipt(args.campaign_id)
        if not receipt:
            print(f"Campaign not found: {args.campaign_id}", file=sys.stderr)
            sys.exit(1)
        import json
        print(json.dumps(receipt, indent=2, default=str))


def _cmd_evaluation_pack(args):
    """Phase 7B: evaluation pack management commands."""
    import os
    ep_command = getattr(args, "ep_command", None)

    if ep_command == "export":
        from .evaluation_pack import EvaluationPackExporter
        exporter = EvaluationPackExporter()
        print(f"Exporting evaluation pack for campaign: {args.campaign_id}")
        out_dir = exporter.export(args.campaign_id, overwrite=getattr(args, "overwrite", False))
        print(f"Evaluation pack exported to: {out_dir}")
        files = os.listdir(out_dir)
        print(f"Files: {', '.join(files)}")

    elif ep_command == "list":
        runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        packs_dir = os.path.join(runtime_root, "evaluation_packs")
        if not os.path.exists(packs_dir):
            print("No evaluation packs directory found.")
            return
        packs = [d for d in os.listdir(packs_dir)
                 if os.path.isdir(os.path.join(packs_dir, d))]
        if not packs:
            print("No evaluation packs found.")
            return
        print(f"Evaluation packs ({len(packs)}):")
        for p in sorted(packs):
            pack_dir = os.path.join(packs_dir, p)
            files = os.listdir(pack_dir)
            print(f"  {p}  ({len(files)} files)")
            for f in sorted(files):
                size = os.path.getsize(os.path.join(pack_dir, f))
                print(f"    {f} ({size:,} bytes)")
    else:
        print("Usage: python -m breakthrough_engine evaluation-pack [export|list]")


def _cmd_review_label(repo: Repository, args):
    """Phase 7D: structured human review label management."""
    import csv as _csv
    import os
    rl_command = getattr(args, "rl_command", None)

    if rl_command == "add":
        label = {
            "campaign_id": args.campaign_id,
            "candidate_id": args.candidate_id,
            "candidate_title": getattr(args, "candidate_title", ""),
            "candidate_role": getattr(args, "role", "finalist"),
            "decision": args.decision,
            "novelty_confidence": getattr(args, "novelty_confidence", 0.5),
            "technical_plausibility": getattr(args, "technical_plausibility", 0.5),
            "commercialization_relevance": getattr(args, "commercialization_relevance", 0.5),
            "key_flaw": getattr(args, "key_flaw", ""),
            "reviewer_note": getattr(args, "note", ""),
            "reviewer": getattr(args, "reviewer", "operator"),
        }
        repo.save_review_label(label)
        print(f"Review label saved: campaign={args.campaign_id[:12]} "
              f"candidate={args.candidate_id[:12]} decision={args.decision}")

    elif rl_command == "list":
        labels = repo.get_review_labels_for_campaign(args.campaign_id)
        if not labels:
            print(f"No review labels found for campaign {args.campaign_id}")
            return
        print(f"Review labels for campaign {args.campaign_id} ({len(labels)}):")
        for lbl in labels:
            print(
                f"  {lbl['candidate_role']:12s}  {lbl['decision']:8s}  "
                f"novelty={lbl.get('novelty_confidence', '?'):.2f}  "
                f"tech={lbl.get('technical_plausibility', '?'):.2f}  "
                f"{lbl.get('candidate_title', '')[:50]}"
            )

    elif rl_command == "export":
        labels = repo.list_all_review_labels()
        if not labels:
            print("No review labels found.")
            return
        output_path = getattr(args, "output", "review_labels.csv")
        fieldnames = [
            "id", "campaign_id", "candidate_id", "candidate_title", "candidate_role",
            "decision", "novelty_confidence", "technical_plausibility",
            "commercialization_relevance", "key_flaw", "reviewer_note", "reviewer", "created_at",
        ]
        with open(output_path, "w", newline="") as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(labels)
        print(f"Exported {len(labels)} review labels to {output_path}")

    else:
        print("Usage: python -m breakthrough_engine review-label [add|list|export]")


# ---------------------------------------------------------------------------
# Phase 8 CLI handlers
# ---------------------------------------------------------------------------

def _cmd_label_completeness(repo: Repository, args):
    """Phase 8: review-label completeness tooling."""
    from .label_completeness import (
        check_label_completeness, export_label_targets_csv, summarize_label_completeness
    )
    lc_command = getattr(args, "lc_command", None)
    if not lc_command:
        print("Usage: python -m breakthrough_engine label-completeness [check|export-targets]")
        return

    campaign_ids = args.campaign_ids

    if lc_command == "check":
        completeness = check_label_completeness(repo.db, campaign_ids)
        print(summarize_label_completeness(completeness))

    elif lc_command == "export-targets":
        completeness = check_label_completeness(repo.db, campaign_ids)
        output_path = getattr(args, "output", "label_targets.csv")
        export_label_targets_csv(completeness, output_path=output_path)
        print(summarize_label_completeness(completeness))
        print(f"\nLabel targets exported to: {output_path}")

    else:
        print("Usage: python -m breakthrough_engine label-completeness [check|export-targets]")


def _cmd_daily(repo: Repository, args):
    """Phase 8: bounded daily automation."""
    from .daily_automation import (
        load_daily_profile, dry_run_profile, list_available_profiles,
        get_daily_status, format_operator_summary
    )
    daily_command = getattr(args, "daily_command", None)

    if not daily_command or daily_command == "list-profiles":
        profiles = list_available_profiles()
        if not profiles:
            print("No daily automation profiles found.")
        else:
            print(f"Available daily automation profiles ({len(profiles)}):")
            for p in profiles:
                print(f"  {p}")
        return

    if daily_command == "status":
        status = get_daily_status(repo)
        print(f"Daily automation status — {status['date']}")
        for profile_name, info in status.get("profiles", {}).items():
            ran = "YES" if info.get("ran_today") else "NO"
            outcome = info.get("last_outcome") or "(not run)"
            print(f"  {profile_name}: ran_today={ran}  last_outcome={outcome}")
        return

    if daily_command == "dry-run":
        profile_name = args.profile_name
        try:
            profile = load_daily_profile(profile_name)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        result = dry_run_profile(profile, repo)
        print(result.operator_summary)
        return

    if daily_command == "run":
        profile_name = args.profile_name
        try:
            profile = load_daily_profile(profile_name)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        from .daily_automation import _today, OUTCOME_ALREADY_RAN_TODAY
        from .models import new_id
        today = _today()

        # Enforce max-runs-per-day (skip if --force)
        force = getattr(args, "force", False)
        if not force and repo.has_daily_run_today(profile_name, today):
            result_dict = {
                "run_id": new_id(),
                "profile_name": profile_name,
                "campaign_id": "",
                "policy_id": "",
                "outcome": OUTCOME_ALREADY_RAN_TODAY,
                "dry_run": False,
                "run_date": today,
                "operator_summary": f"Profile '{profile_name}' already ran today ({today}). Skipping.",
            }
            print(result_dict["operator_summary"])
            return

        print(f"Running daily profile: {profile_name}")
        print(f"  Campaign profile: {profile.campaign_profile}")
        print(f"  Domain: {profile.domain}")
        print(f"  (Use dry-run to preview without executing)")
        print()

        # Run the campaign via campaign manager
        from .campaign_manager import CampaignManager, CampaignProfile
        from .policy_registry import PolicyRegistry
        from .daily_automation import (
            OUTCOME_COMPLETED_WITH_DRAFT, OUTCOME_COMPLETED_NO_DRAFT,
            OUTCOME_ABORTED_PREFLIGHT, OUTCOME_ABORTED_RUNTIME,
            build_review_queue_item, format_operator_summary, DailyRunResult
        )
        from datetime import datetime, timezone

        reg = PolicyRegistry(repo)
        champion = reg.get_champion()
        policy_id = champion.id

        run_id = new_id()
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        campaign_id = ""
        outcome = OUTCOME_ABORTED_RUNTIME
        error_msg = ""
        review_queue_item_id = ""

        try:
            from .campaign_manager import load_campaign_profile as _load_cp
            mgr = CampaignManager(repo)
            campaign_profile_obj = _load_cp(profile.campaign_profile)
            receipt = mgr.run_campaign(campaign_profile_obj, strict_preflight=profile.require_integrity_ok)
            campaign_id = receipt.campaign_id
            from .campaign_manager import CampaignStatus as _CampaignStatus
            has_draft = receipt.status == _CampaignStatus.COMPLETED_WITH_DRAFT.value
            outcome = OUTCOME_COMPLETED_WITH_DRAFT if has_draft else OUTCOME_COMPLETED_NO_DRAFT
            # Build campaign_result dict from receipt for downstream consumers
            campaign_result = {
                "campaign_id": campaign_id,
                "has_draft": has_draft,
                "champion_candidate_id": receipt.champion_candidate_id,
                "champion_title": receipt.champion_candidate_title,
                "champion_score": 0.0,
                "finalist_count": receipt.total_shortlisted,
                "champion": {
                    "id": receipt.champion_candidate_id,
                    "title": receipt.champion_candidate_title,
                },
            }

            # Insert into review queue if draft found and profile requests it
            if profile.insert_review_queue and has_draft:
                item = build_review_queue_item(
                    daily_run_id=run_id,
                    profile=profile,
                    campaign_result=campaign_result,
                    policy_id=policy_id,
                )
                review_queue_item_id = repo.insert_review_queue_item(item)

        except Exception as e:
            outcome = OUTCOME_ABORTED_RUNTIME
            error_msg = str(e)
            logger.error("Daily run failed: %s", e)

        completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Log the run
        repo.insert_daily_run({
            "id": run_id,
            "profile_name": profile_name,
            "campaign_id": campaign_id,
            "policy_id": policy_id,
            "outcome": outcome,
            "dry_run": False,
            "error_message": error_msg,
            "started_at": started_at,
            "completed_at": completed_at,
            "run_date": today,
        })

        from .daily_automation import DailyRunResult
        result = DailyRunResult(
            run_id=run_id,
            profile_name=profile_name,
            campaign_id=campaign_id,
            policy_id=policy_id,
            outcome=outcome,
            dry_run=False,
            error_message=error_msg,
            started_at=started_at,
            completed_at=completed_at,
            run_date=today,
            review_queue_item_id=review_queue_item_id,
        )
        print(format_operator_summary(result, profile))
        return

    print("Usage: python -m breakthrough_engine daily [run|dry-run|status|list-profiles]")


def _cmd_review_queue(repo: Repository, args):
    """Phase 8: review queue management."""
    rq_command = getattr(args, "rq_command", None)

    if not rq_command:
        print("Usage: python -m breakthrough_engine review-queue [list|inspect|mark-reviewed]")
        return

    if rq_command == "list":
        status = getattr(args, "status", "pending")
        items = repo.list_review_queue(review_status=status)
        if not items:
            print(f"No review queue items with status='{status}'.")
            return
        print(f"Review queue — {status} ({len(items)} items):")
        print(f"{'ID[:8]':<10} {'Campaign':<20} {'Profile':<35} {'Score':<8} {'Champion Title'}")
        print("-" * 100)
        for item in items:
            print(
                f"{item['id'][:8]:<10} {item['campaign_id'][:18]:<20} "
                f"{item['profile_name']:<35} {item.get('champion_score', 0.0):.3f}  "
                f"{item.get('champion_title', '')[:40]}"
            )

    elif rq_command == "inspect":
        item_id = args.item_id
        items = repo.list_review_queue(review_status="all")
        item = next((i for i in items if i["id"].startswith(item_id)), None)
        if item is None:
            print(f"Review queue item not found: {item_id}", file=sys.stderr)
            sys.exit(1)
        print(f"Review Queue Item: {item['id']}")
        print(f"  Campaign: {item['campaign_id']}")
        print(f"  Profile: {item['profile_name']}")
        print(f"  Policy: {item['policy_id']}")
        print(f"  Champion: {item['champion_title']}")
        print(f"  Score: {item.get('champion_score', 0.0):.4f}")
        print(f"  Falsification: {item.get('falsification_summary', '')}")
        print(f"  Rationale: {item.get('rationale', '')[:200]}")
        print(f"  Outcome: {item['outcome']}")
        print(f"  Review status: {item['review_status']}")
        print(f"  Inserted at: {item.get('inserted_at', '')}")
        if item.get("reviewed_at"):
            print(f"  Reviewed at: {item['reviewed_at']} by {item.get('reviewer', '?')}")
        print()
        print(f"To add review label:")
        print(f"  python -m breakthrough_engine review-label add \\")
        print(f"    --campaign-id {item['campaign_id']} \\")
        print(f"    --candidate-id {item.get('champion_candidate_id', '(unknown)')} \\")
        print(f"    --role champion --decision approve \\")
        print(f"    --novelty-confidence 0.8 --technical-plausibility 0.8 \\")
        print(f"    --commercialization-relevance 0.7")

    elif rq_command == "mark-reviewed":
        item_id = args.item_id
        reviewer = getattr(args, "reviewer", "operator")
        repo.mark_review_queue_item_reviewed(item_id, reviewer=reviewer)
        print(f"Marked review queue item {item_id[:12]} as reviewed (reviewer={reviewer})")

    else:
        print("Usage: python -m breakthrough_engine review-queue [list|inspect|mark-reviewed]")


def _cmd_challenger_trial(repo: Repository, args):
    """Phase 8B challenger-vs-champion trial commands."""
    if not hasattr(args, "ct_command") or not args.ct_command:
        print("Usage: python -m breakthrough_engine challenger-trial [build|show]")
        return

    if args.ct_command == "show":
        import json as _json
        trial_dir = args.trial_dir
        summary_path = os.path.join(trial_dir, "challenger_vs_champion_summary.json")
        if not os.path.exists(summary_path):
            print(f"Trial summary not found: {summary_path}", file=sys.stderr)
            sys.exit(1)
        with open(summary_path) as f:
            summary = _json.load(f)
        print(_json.dumps(summary, indent=2))

    elif args.ct_command == "build":
        from .challenger_trial import (
            build_arm_from_campaign_ids,
            compare_arms,
            export_trial_csv,
            export_trial_summary_json,
            export_trial_summary_md,
            ChallengerTrialResult,
        )
        from .policy_registry import PolicyRegistry
        from .models import new_id
        from .reviewed_baseline import get_registry as get_baseline_registry
        from datetime import datetime, timezone

        registry = PolicyRegistry(repo)
        challenger_id = args.challenger_id
        challenger = registry.get_policy(challenger_id)
        if challenger is None:
            print(f"Error: challenger policy not found: {challenger_id}", file=sys.stderr)
            sys.exit(1)

        champion = registry.get_champion()

        output_dir = args.output_dir
        os.makedirs(output_dir, exist_ok=True)

        print(f"Building challenger trial summary...")
        print(f"  Champion: {champion.name} ({champion.id})")
        print(f"  Challenger: {challenger.name} ({challenger.id})")
        print(f"  Champion campaigns: {args.champion_campaigns}")
        print(f"  Challenger campaigns: {args.challenger_campaigns}")

        champion_arm = build_arm_from_campaign_ids(
            repo.db, args.champion_campaigns, champion.id, champion.name
        )
        challenger_arm = build_arm_from_campaign_ids(
            repo.db, args.challenger_campaigns, challenger.id, challenger.name
        )

        # Get baseline mean score for regression guard
        baseline_mean = None
        baseline_id = getattr(args, "baseline", "phase8_reviewed")
        try:
            baseline_reg = get_baseline_registry()
            b = baseline_reg.load(baseline_id)
            if b and b.summary_statistics:
                baseline_mean = b.summary_statistics.get("champion_score_mean")
        except Exception as e:
            logger.debug("Could not load baseline for regression guard: %s", e)

        comparison = compare_arms(champion_arm, challenger_arm, baseline_mean_score=baseline_mean)

        trial_id = f"phase8b_trial_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        result = ChallengerTrialResult(
            trial_id=trial_id,
            trial_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            champion_arm=champion_arm,
            challenger_arm=challenger_arm,
            comparison=comparison,
            profile_used=getattr(args, "profile", "eval_clean_energy_30m"),
            total_campaigns=champion_arm.campaign_count + challenger_arm.campaign_count,
            started_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            completed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        csv_path = os.path.join(output_dir, "policy_trials.csv")
        json_path = os.path.join(output_dir, "challenger_vs_champion_summary.json")
        md_path = os.path.join(output_dir, "challenger_vs_champion_summary.md")

        export_trial_csv(result, csv_path)
        export_trial_summary_json(result, json_path)
        export_trial_summary_md(result, md_path)

        print(f"\nTrial summary exported to {output_dir}")
        print(f"  {csv_path}")
        print(f"  {json_path}")
        print(f"  {md_path}")
        print()
        print(f"Champion mean score:   {champion_arm.mean_champion_score:.5f}" if champion_arm.mean_champion_score else "Champion mean: N/A")
        print(f"Challenger mean score: {challenger_arm.mean_champion_score:.5f}" if challenger_arm.mean_champion_score else "Challenger mean: N/A")
        if comparison.champion_score_delta is not None:
            print(f"Score delta (chal-champ): {comparison.champion_score_delta:+.5f}")
        print()
        print(f"Promotion assessment: {comparison.promotion_assessment.upper()}")
        print(f"  (Automatic promotion is OFF — operator must manually promote if recommended)")
        for note in comparison.promotion_notes:
            print(f"  - {note}")

    else:
        print("Usage: python -m breakthrough_engine challenger-trial [build|show]")


# ---------------------------------------------------------------------------
# PV domain loop
# ---------------------------------------------------------------------------

def _cmd_pv(repo: Repository, args):
    """PV I-V characterization optimization loop."""
    pv_command = getattr(args, "pv_command", None)

    if not pv_command:
        print("Usage: python -m breakthrough_engine pv [run|dry-run|status|memory|benchmark]")
        return

    if pv_command == "dry-run":
        from .pv_loop import generate_pv_candidates
        from .pv_domain import DEFAULT_CELL_PARAMS as PV_DEFAULTS
        n = getattr(args, "candidates", 6)
        seed = getattr(args, "seed", None)
        prior_lessons = repo.list_idea_memory("pv_iv", limit=50)
        candidates = generate_pv_candidates(n_candidates=n, seed=seed, prior_lessons=prior_lessons)
        print(f"PV dry-run: {len(candidates)} candidates generated (seed={seed})")
        print()
        for i, c in enumerate(candidates, 1):
            print(f"  {i}. {c.title}")
            print(f"     Family: {c.family}")
            print(f"     Rationale: {c.rationale}")
            changed = []
            for param in ("R_s", "R_sh_ref", "I_L_ref", "I_o_ref", "a_ref"):
                base_val = PV_DEFAULTS.get(param, 0)
                cand_val = c.parameters.get(param, base_val)
                if base_val and abs(cand_val - base_val) / max(abs(base_val), 1e-15) > 0.01:
                    changed.append(f"{param}: {base_val} → {cand_val:.4g}")
            if changed:
                print(f"     Changes: {'; '.join(changed)}")
            print()
        return

    if pv_command == "run":
        from .pv_loop import PVOptimizationLoop

        n = getattr(args, "candidates", 6)
        threshold = getattr(args, "threshold", 0.55)
        seed = getattr(args, "seed", None)
        run_id = f"pv_run_{seed or 'auto'}"

        print(f"PV Run: {n} candidates, threshold={threshold}, seed={seed}")
        print("=" * 60)

        loop = PVOptimizationLoop(
            repo, n_candidates=n, promotion_threshold=threshold, seed=seed,
        )
        result = loop.run(run_id=run_id)
        summary = result.summary()

        print(f"\nTotal candidates: {summary['total_candidates']}")
        print(f"Promoted: {summary['promoted']}, Rejected: {summary['rejected']}, Hard-fail: {summary['hard_fail']}")
        print(f"Baseline Pmax: {result.baseline_metrics.get('Pmax', 0):.2f}W")
        print(f"Baseline FF: {result.baseline_metrics.get('fill_factor', 0):.4f}")

        if result.best_promoted:
            bp = result.best_promoted
            print(f"\nBest promoted: {bp.candidate.title}")
            print(f"  Score: {bp.evaluation.final_score:.4f}")
            m = bp.experiment_metrics
            print(f"  Pmax: {m.get('Pmax', 0):.2f}W")
            print(f"  Fill factor: {m.get('fill_factor', 0):.4f}")
            print(f"  Efficiency: {m.get('efficiency', 0):.2f}%")
            if bp.promotion_caveats:
                print(f"  Caveats ({len(bp.promotion_caveats)}):")
                for caveat in bp.promotion_caveats:
                    print(f"    - {caveat}")

        # Export summary artifact
        runtime_dir = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        artifact_dir = os.path.join(runtime_dir, "pv_loop")
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, f"{run_id}.json")
        with open(artifact_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"Artifact: {artifact_path}")
        return

    if pv_command == "status":
        candidates = repo.list_domain_candidates("pv_iv", limit=20)
        promos = repo.list_promotion_records("pv_iv", limit=20)
        print(f"PV loop status:")
        print(f"  Domain candidates: {len(candidates)}")
        print(f"  Promotion records: {len(promos)}")
        promoted = [p for p in promos if p.get("decision") == "promoted"]
        rejected = [p for p in promos if p.get("decision") == "rejected"]
        print(f"  Promoted: {len(promoted)}, Rejected: {len(rejected)}")
        if candidates:
            print(f"\n  Recent candidates:")
            for c in candidates[:5]:
                print(f"    {c.get('title', 'unknown')} — {c.get('status', 'unknown')}")
        return

    if pv_command == "memory":
        ideas = repo.list_idea_memory("pv_iv", limit=20)
        exp_mem = repo.list_experiment_memory("pv_iv", limit=20)
        print(f"PV idea memory: {len(ideas)} entries")
        for m in ideas[:10]:
            print(f"  {m['candidate_title']} — {m['outcome']}")
            if m['lesson']:
                print(f"    Lesson: {m['lesson']}")
        print()
        print(f"PV experiment memory: {len(exp_mem)} entries")
        for m in exp_mem[:10]:
            print(f"  {m['template_name']} — candidate {m['candidate_id'][:8]}")
            if m['weakness_exposed']:
                print(f"    Weakness: {m['weakness_exposed']}")
        return

    if pv_command == "benchmark":
        from .pv_loop import run_pv_benchmark

        n = getattr(args, "candidates", 6)
        threshold = getattr(args, "threshold", 0.55)
        seed = getattr(args, "seed", 42)

        print(f"PV Benchmark: {n} candidates, threshold={threshold}, seed={seed}")
        print("=" * 60)

        report = run_pv_benchmark(repo, n_candidates=n, seed=seed, promotion_threshold=threshold)

        # Print baseline
        base = report["baseline_candidate"]["baseline_metrics"]
        print(f"\nBaseline (default cell params):")
        print(f"  Pmax={base.get('Pmax', 0):.2f}W  FF={base.get('fill_factor', 0):.4f}  "
              f"eff={base.get('efficiency', 0):.2f}%")

        # Print best candidate
        if report["best_candidate"]:
            bc = report["best_candidate"]
            m = bc["metrics"]
            print(f"\nBest candidate: {bc['title']}")
            print(f"  Score: {bc['score']:.4f}")
            print(f"  Pmax={m.get('Pmax', 0):.2f}W  FF={m.get('fill_factor', 0):.4f}  "
                  f"eff={m.get('efficiency', 0):.2f}%")

        # Print robustness
        if report["robustness_profile"]:
            rp = report["robustness_profile"]
            print(f"\nRobustness profile:")
            print(f"  Worst-case Pmax delta: {rp.get('worst_case_pmax_delta', 0):.1%}")
            print(f"  Temperature sensitivity: {rp.get('temperature_sensitivity', 0):.1%}")
            print(f"  Combined fragility: {rp.get('combined_fragility', 0):.1%}")
            print(f"  Efficiency stability: {rp.get('efficiency_stability', 0):.4f}")

        # Print caveats
        if report["caveats"]:
            print(f"\nCaveats ({len(report['caveats'])}):")
            for caveat in report["caveats"]:
                print(f"  - {caveat}")

        # Print reference comparison
        ref = report["reference_comparison"]
        ref_m = ref.get("reference_metrics", {})
        print(f"\nHeld-out reference ({ref.get('reference_name', 'unknown')}):")
        print(f"  Pmax={ref_m.get('Pmax', 0):.2f}W  FF={ref_m.get('fill_factor', 0):.4f}  "
              f"eff={ref_m.get('efficiency', 0):.2f}%")
        if "pmax_vs_reference" in ref:
            print(f"  Candidate vs reference Pmax: {ref['pmax_vs_reference']:.1%}")
        if "within_reference_envelope" in ref:
            status = "PASS" if ref["within_reference_envelope"] else "FAIL"
            print(f"  Within reference envelope: {status}")

        # Print promotion decision
        print(f"\nPromotion decision: {report['promotion_decision']}")
        print(f"\nSummary: {report['summary']['promoted']} promoted, "
              f"{report['summary']['rejected']} rejected, "
              f"{report['summary']['hard_fail']} hard-fail")

        # Export report artifact
        runtime_dir = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        artifact_dir = os.path.join(runtime_dir, "pv_loop")
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, f"pv_benchmark_{seed}.json")
        with open(artifact_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nBenchmark report: {artifact_path}")
        return

    print("Usage: python -m breakthrough_engine pv [run|dry-run|status|memory|benchmark]")


# ---------------------------------------------------------------------------
# Battery domain loop
# ---------------------------------------------------------------------------

def _resolve_battery_sidecar(args):
    """Resolve sidecar from CLI flags: --no-sidecar, --mock-sidecar, or auto."""
    if getattr(args, "no_sidecar", False):
        return None
    if getattr(args, "mock_sidecar", False):
        from .battery_sidecar import MockPyBaMMSidecar
        seed = getattr(args, "seed", 42) or 42
        return MockPyBaMMSidecar(seed=seed)
    # Auto: try live sidecar, fall back to None (ECM-only)
    from .battery_sidecar import PyBaMMSidecar
    sidecar = PyBaMMSidecar()
    return sidecar if sidecar.is_available() else None


def _cmd_battery(repo: Repository, args):
    """Battery ECM + cycle characterization optimization loop."""
    battery_command = getattr(args, "battery_command", None)

    if not battery_command:
        print("Usage: python -m breakthrough_engine battery [run|dry-run|status|memory|benchmark]")
        return

    if battery_command == "dry-run":
        from .battery_loop import generate_battery_candidates
        n = getattr(args, "candidates", 6)
        seed = getattr(args, "seed", None)
        prior_lessons = repo.list_idea_memory("battery_ecm", limit=50)
        candidates = generate_battery_candidates(n_candidates=n, seed=seed, prior_lessons=prior_lessons)
        print(f"Battery dry-run: {len(candidates)} candidates generated (seed={seed})")
        print()
        for i, c in enumerate(candidates):
            print(f"  {i+1}. {c.title}")
            print(f"     Family: {c.family or c.title.split('variant')[0].replace('Battery ', '').strip()}")
            print(f"     Rationale: {c.rationale}")
            changed = []
            from .battery_domain import DEFAULT_CELL_PARAMS as BAT_DEFAULTS
            for param in ("R0_mohm", "R1_mohm", "capacity_ah", "coulombic_eff", "fade_rate_per_cycle"):
                base_val = BAT_DEFAULTS.get(param, 0)
                cand_val = c.parameters.get(param, base_val)
                if base_val and abs(cand_val - base_val) / max(abs(base_val), 1e-15) > 0.01:
                    changed.append(f"{param}: {base_val} → {cand_val:.4g}")
            if changed:
                print(f"     Changes: {'; '.join(changed)}")
            print()
        return

    if battery_command == "run":
        from .battery_loop import BatteryOptimizationLoop
        n = getattr(args, "candidates", 6)
        threshold = getattr(args, "threshold", 0.84)
        seed = getattr(args, "seed", None)
        run_id = f"battery_run_{seed or 'auto'}"

        # Sidecar configuration
        sidecar = _resolve_battery_sidecar(args)
        sidecar_label = "mock" if getattr(args, "mock_sidecar", False) else ("off" if getattr(args, "no_sidecar", False) else "auto")

        print(f"Battery Run: {n} candidates, threshold={threshold}, seed={seed}, sidecar={sidecar_label}")
        print("=" * 60)

        loop = BatteryOptimizationLoop(repo, n_candidates=n, promotion_threshold=threshold, seed=seed, sidecar=sidecar)
        result = loop.run(run_id=run_id)
        summary = result.summary()

        print(f"\nTotal candidates: {summary['total_candidates']}")
        print(f"Promoted: {summary['promoted']}, Rejected: {summary['rejected']}, Hard-fail: {summary['hard_fail']}")
        print(f"Baseline capacity: {summary['baseline_capacity']:.3f} Ah")
        print(f"Baseline resistance: {summary['baseline_resistance']:.1f} mOhm")

        if result.best_promoted:
            bp = result.best_promoted
            print(f"\nBest promoted: {bp.candidate.title}")
            print(f"  Score: {bp.evaluation.final_score:.4f}")
            m = bp.experiment_metrics
            print(f"  Capacity: {m.get('discharge_capacity', 0):.3f} Ah")
            print(f"  Coulombic eff: {m.get('coulombic_efficiency', 0):.2f}%")
            print(f"  Resistance: {m.get('internal_resistance', 0):.1f} mOhm")
            if bp.promotion_caveats:
                print(f"  Caveats ({len(bp.promotion_caveats)}):")
                for caveat in bp.promotion_caveats:
                    print(f"    - {caveat}")

        # Write artifact
        runtime_dir = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        artifact_dir = os.path.join(runtime_dir, "battery_loop")
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, f"battery_run_{seed or 'auto'}.json")
        with open(artifact_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"\nArtifact: {artifact_path}")
        return

    if battery_command == "status":
        candidates = repo.list_domain_candidates("battery_ecm", limit=20)
        promos = repo.list_promotion_records("battery_ecm", limit=20)
        print(f"Battery loop status:")
        print(f"  Domain candidates: {len(candidates)}")
        print(f"  Promotion records: {len(promos)}")
        promoted = [p for p in promos if p.get("decision") == "promoted"]
        rejected = [p for p in promos if p.get("decision") == "rejected"]
        print(f"  Promoted: {len(promoted)}, Rejected: {len(rejected)}")
        if candidates:
            print(f"\n  Recent candidates:")
            for c in candidates[:5]:
                print(f"    {c.get('title', 'unknown')} — {c.get('status', 'unknown')}")
        return

    if battery_command == "memory":
        ideas = repo.list_idea_memory("battery_ecm", limit=20)
        exp_mem = repo.list_experiment_memory("battery_ecm", limit=20)
        print(f"Battery idea memory: {len(ideas)} entries")
        for m in ideas[:10]:
            print(f"  {m['candidate_title']} — {m['outcome']}")
            if m['lesson']:
                print(f"    Lesson: {m['lesson']}")
        print()
        print(f"Battery experiment memory: {len(exp_mem)} entries")
        for m in exp_mem[:10]:
            print(f"  {m['template_name']} — candidate {m['candidate_id'][:8]}")
            if m['weakness_exposed']:
                print(f"    Weakness: {m['weakness_exposed']}")
        return

    if battery_command == "benchmark":
        from .battery_loop import run_battery_benchmark

        n = getattr(args, "candidates", 6)
        threshold = getattr(args, "threshold", 0.84)
        seed = getattr(args, "seed", 42)
        sidecar = _resolve_battery_sidecar(args)
        sidecar_label = "mock" if getattr(args, "mock_sidecar", False) else ("off" if getattr(args, "no_sidecar", False) else "auto")

        print(f"Battery Benchmark: {n} candidates, threshold={threshold}, seed={seed}, sidecar={sidecar_label}")
        print("=" * 60)

        report = run_battery_benchmark(repo, n_candidates=n, seed=seed, promotion_threshold=threshold, sidecar=sidecar)

        # Print baseline
        base = report["baseline_candidate"]["baseline_metrics"]
        print(f"\nBaseline (default cell params):")
        print(f"  Capacity={base.get('discharge_capacity', 0):.3f}Ah  "
              f"CE={base.get('coulombic_efficiency', 0):.2f}%  "
              f"R={base.get('internal_resistance', 0):.1f}mOhm")

        # Print best candidate
        if report["best_candidate"]:
            bc = report["best_candidate"]
            m = bc["metrics"]
            print(f"\nBest candidate: {bc['title']}")
            print(f"  Score: {bc['score']:.4f}")
            print(f"  Capacity={m.get('discharge_capacity', 0):.3f}Ah  "
                  f"CE={m.get('coulombic_efficiency', 0):.2f}%  "
                  f"R={m.get('internal_resistance', 0):.1f}mOhm")

        if report.get("robustness_profile"):
            rp = report["robustness_profile"]
            print(f"\nRobustness profile:")
            print(f"  Worst-case capacity delta: {rp.get('worst_case_capacity_delta', 0):.1%}")
            print(f"  C-rate sensitivity: {rp.get('crate_sensitivity', 0):.1%}")
            print(f"  Thermal sensitivity: {rp.get('thermal_sensitivity', 0):.1%}")
            print(f"  Capacity retention: {rp.get('capacity_retention', 0):.1f}%")
            print(f"  Fade rate: {rp.get('fade_rate', 0):.4f}%/cycle")

        if report.get("caveats"):
            print(f"\nCaveats ({len(report['caveats'])}):")
            for c in report["caveats"]:
                print(f"  - {c}")

        # Held-out reference
        ref = report["reference_comparison"]
        ref_m = ref.get("reference_metrics", {})
        print(f"\nHeld-out reference ({ref['reference_name']}):")
        print(f"  Capacity={ref_m.get('discharge_capacity', 0):.3f}Ah  "
              f"CE={ref_m.get('coulombic_efficiency', 0):.2f}%  "
              f"R={ref_m.get('internal_resistance', 0):.1f}mOhm")
        if "capacity_vs_reference" in ref:
            print(f"  Candidate vs reference capacity: {ref['capacity_vs_reference']:.1%}")
        if "within_reference_envelope" in ref:
            print(f"  Within reference envelope: {'PASS' if ref['within_reference_envelope'] else 'FAIL'}")

        print(f"\nPromotion decision: {report['promotion_decision']}")
        s = report["summary"]
        print(f"\nSummary: {s['promoted']} promoted, {s['rejected']} rejected, {s['hard_fail']} hard-fail")

        # Export artifact
        runtime_dir = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        artifact_dir = os.path.join(runtime_dir, "battery_loop")
        os.makedirs(artifact_dir, exist_ok=True)
        artifact_path = os.path.join(artifact_dir, f"battery_benchmark_{seed}.json")
        with open(artifact_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nBenchmark report: {artifact_path}")
        return

    if battery_command == "briefs":
        from .battery_review import BriefStore
        store = BriefStore()
        briefs = store.list_briefs()
        if not briefs:
            print("No battery decision briefs found.")
            return
        print(f"Battery Decision Briefs ({len(briefs)}):")
        for b in briefs:
            state = b.get("review_state", "?")
            score = b.get("final_score", 0)
            print(f"  {b.get('id', '?')[:12]}  score={score:.3f}  state={state}  {b.get('title', '')}")
        return

    if battery_command == "inspect":
        from .battery_review import BriefStore
        store = BriefStore()
        brief = store.get_brief(args.brief_id)
        if not brief:
            print(f"Brief not found: {args.brief_id}")
            return
        print(json.dumps(brief, indent=2, default=str))
        return

    if battery_command == "review":
        from .battery_review import BriefStore
        store = BriefStore()
        record = store.update_review_state(
            args.brief_id, args.state,
            reviewer=args.reviewer, notes=args.notes,
        )
        if not record:
            print(f"Brief not found: {args.brief_id}")
            return
        print(f"Review recorded: {args.brief_id} → {args.state}")
        if args.notes:
            print(f"  Notes: {args.notes}")
        return

    if battery_command == "export":
        from .battery_review import BriefStore
        store = BriefStore()
        path = store.export_brief(args.brief_id)
        if not path:
            print(f"Brief not found: {args.brief_id}")
            return
        print(f"Exported: {path}")
        return

    print("Usage: python -m breakthrough_engine battery [run|dry-run|status|memory|benchmark|briefs|inspect|review|export]")


# ---------------------------------------------------------------------------
# Phase 10A: Ingest
# ---------------------------------------------------------------------------

def _cmd_ingest(repo: Repository, args):
    if not hasattr(args, "ingest_command") or not args.ingest_command:
        print("Usage: python -m breakthrough_engine ingest [run|status]")
        return

    if args.ingest_command == "run":
        from .paper_ingestion import PaperIngestionWorker, IngestionConfig

        config = IngestionConfig(
            domain=args.domain,
            limit=args.limit,
            compress=args.compress,
        )
        worker = PaperIngestionWorker(repo, config=config)

        if args.source == "findings":
            stats = worker.ingest_from_findings(domain=args.domain, limit=args.limit)
        else:
            stats = worker.ingest_from_evidence_items(domain=args.domain, limit=args.limit)

        print(f"Ingestion complete: {json.dumps(stats, indent=2)}")

    elif args.ingest_command == "status":
        domain = args.domain if hasattr(args, "domain") else ""
        total = repo.count_paper_segments(domain=domain)
        by_status = {}
        for st in ("ingested", "scored", "extracted", "extraction_failed", "skipped"):
            count = repo.count_paper_segments(domain=domain, status=st)
            if count > 0:
                by_status[st] = count
        print(f"Paper segments (domain={domain or 'all'}): {total} total")
        for status, count in by_status.items():
            print(f"  {status}: {count}")


# ---------------------------------------------------------------------------
# Phase 10A: KG
# ---------------------------------------------------------------------------

def _cmd_kg(repo: Repository, args):
    if not hasattr(args, "kg_command") or not args.kg_command:
        print("Usage: python -m breakthrough_engine kg [extract|stats|compare|writeback-status]")
        return

    if args.kg_command == "extract":
        from .kg_extractor import EntityRelationExtractor, ExtractionConfig

        config = ExtractionConfig()
        extractor = EntityRelationExtractor(repo, config=config, mock=args.mock)
        stats = extractor.extract_from_segments(
            domain=args.domain, limit=args.limit,
        )
        print(f"Extraction complete: {json.dumps(stats, indent=2)}")

    elif args.kg_command == "stats":
        entities = repo.list_kg_entities(limit=1000)
        relations = repo.list_kg_relations(limit=1000)
        segments = repo.count_paper_segments()

        print("KG Statistics:")
        print(f"  Paper segments: {segments}")
        print(f"  Entities: {len(entities)}")
        print(f"  Relations: {len(relations)}")

        if entities:
            type_counts: dict[str, int] = {}
            for e in entities:
                t = e.get("entity_type", "unknown")
                type_counts[t] = type_counts.get(t, 0) + 1
            print("  Entity types:")
            for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
                print(f"    {t}: {c}")

    elif args.kg_command == "compare":
        from .evidence_source import DemoFixtureSource
        from .kg_retrieval import KGEvidenceSource
        from .kg_comparison import RetrievalComparisonHarness

        current = DemoFixtureSource()
        shadow = KGEvidenceSource(repo)
        harness = RetrievalComparisonHarness(current, shadow)
        result = harness.compare(domain=args.domain, limit=args.limit)

        import os
        os.makedirs(args.output_dir, exist_ok=True)
        harness.export_json(result, os.path.join(args.output_dir, "comparison.json"))
        harness.export_markdown(result, os.path.join(args.output_dir, "comparison.md"))
        harness.export_csv(result, os.path.join(args.output_dir, "comparison.csv"))

        print(f"Comparison verdict: {result.verdict}")
        for note in result.notes:
            print(f"  - {note}")
        print(f"Artifacts: {args.output_dir}/")

    elif args.kg_command == "writeback-status":
        domain = args.domain if hasattr(args, "domain") else ""
        from .kg_writer import list_active_findings, list_shadow_findings
        active = list_active_findings(repo, domain=domain)
        shadow = list_shadow_findings(repo, domain=domain)
        print(f"KG Findings (domain={domain or 'all'}):")
        print(f"  Active: {len(active)}")
        print(f"  Shadow: {len(shadow)}")
        for f in active[:5]:
            print(f"    [{f['id'][:8]}] {f.get('title', '')[:60]}")
        for f in shadow[:5]:
            print(f"    [{f['id'][:8]}] (shadow) {f.get('title', '')[:60]}")
