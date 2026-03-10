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
import sys

from .config_loader import list_programs, load_program, validate_program
from .db import Repository, init_db
from .orchestrator import BreakthroughOrchestrator
from .reporting import generate_markdown_report, save_reports


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
    policy_rollback_p = policy_sub.add_parser("rollback", help="Roll back champion to previous")
    policy_rollback_p.add_argument("--reason", default="", help="Rollback reason")

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
        print("Usage: python -m breakthrough_engine baseline compare")
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


def _cmd_policy(repo: Repository, args):
    if not hasattr(args, "policy_command") or not args.policy_command:
        print("Usage: python -m breakthrough_engine policy [list|show|promote|rollback]")
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
        ok = registry.promote_to_probation(args.policy_id, evidence={"reason": args.reason})
        if ok:
            print(f"Policy {args.policy_id} promoted to probation.")
        else:
            print(f"Promotion failed: criteria not met or insufficient trials.")
            sys.exit(1)

    elif args.policy_command == "rollback":
        ok = registry.rollback_champion(reason=args.reason or "operator rollback")
        if ok:
            print("Champion rolled back to previous.")
        else:
            print("Rollback failed: no previous champion found.")
            sys.exit(1)


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

        manager = CampaignManager(repo=repo, db_path=getattr(args, "db", None))
        print(f"Launching campaign: {profile.profile_name} ({profile.profile_type})")
        if dry_run:
            print("  (dry-run mode — preflight only)")

        receipt = manager.run_campaign(profile, strict_preflight=strict, dry_run=dry_run)

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
