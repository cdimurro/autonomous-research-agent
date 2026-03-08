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
