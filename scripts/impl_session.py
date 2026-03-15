#!/usr/bin/env python3
"""Implementation Safety Harness — Session & Gate Management.

Usage:
    python scripts/impl_session.py init --scope "..." [--risk high] [--files a.py b.py]
    python scripts/impl_session.py verify
    python scripts/impl_session.py review-status
    python scripts/impl_session.py gate
    python scripts/impl_session.py clean
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = REPO_ROOT / "runtime" / "sessions"
ACTIVE_SESSION_FILE = SESSION_DIR / "active_session.json"
REVIEW_ARTIFACT_FILE = SESSION_DIR / "active_review.json"


# ── Session init ──────────────────────────────────────────────────────────

def cmd_init(args):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()
    session = {
        "session_id": f"ISH-{uuid.uuid4().hex[:8]}",
        "branch": branch,
        "execution_mode": args.mode,
        "scope": args.scope,
        "files_expected_to_change": args.files or [],
        "risk_level": args.risk,
        "tests_expected_to_run": args.tests or [],
        "review_gate_required": True,
        "commit_blocked_until_gate_pass": True,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": args.notes or "",
    }
    ACTIVE_SESSION_FILE.write_text(json.dumps(session, indent=2) + "\n")
    print(f"Session created: {session['session_id']}")
    print(f"  Branch: {branch}")
    print(f"  Scope:  {args.scope}")
    print(f"  Risk:   {args.risk}")
    print(f"  Artifact: {ACTIVE_SESSION_FILE}")
    return 0


# ── Static / wiring checks ───────────────────────────────────────────────

def _check_scope_drift(session: dict) -> list[str]:
    """Check if changed files are outside declared scope."""
    issues = []
    declared = set(session.get("files_expected_to_change", []))
    if not declared:
        return []  # no declared files = skip drift check
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        staged = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"], cwd=REPO_ROOT, text=True
        ).strip()
        untracked = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=REPO_ROOT, text=True
        ).strip()
    except subprocess.CalledProcessError:
        return []
    changed = set()
    for blob in (diff_output, staged, untracked):
        for line in blob.splitlines():
            if line.strip():
                changed.add(line.strip())
    # Filter to code files only (ignore runtime artifacts, reviews, sessions)
    code_changed = {f for f in changed if not f.startswith("runtime/")}
    undeclared = code_changed - declared
    if undeclared:
        issues.append(f"Scope drift: files changed but not declared in session: {sorted(undeclared)}")
    return issues


def _check_review_artifact_exists() -> list[str]:
    if not REVIEW_ARTIFACT_FILE.exists():
        return ["Codex review artifact missing: runtime/sessions/active_review.json"]
    return []


def _check_review_no_blockers() -> list[str]:
    if not REVIEW_ARTIFACT_FILE.exists():
        return ["Cannot check blockers — review artifact missing"]
    review = json.loads(REVIEW_ARTIFACT_FILE.read_text())
    blockers = review.get("blockers", [])
    if blockers:
        return [f"Codex review has {len(blockers)} blocker(s): {blockers}"]
    return []


def cmd_verify(args):
    """Run static checks + targeted tests."""
    if not ACTIVE_SESSION_FILE.exists():
        print("FAIL: No active session. Run: python scripts/impl_session.py init --scope '...'")
        return 1
    session = json.loads(ACTIVE_SESSION_FILE.read_text())
    print(f"Verifying session {session['session_id']}...")

    all_issues: list[str] = []

    # Static checks
    all_issues.extend(_check_scope_drift(session))

    # Run tests
    test_targets = session.get("tests_expected_to_run", [])
    risk = session.get("risk_level", "low")

    if test_targets:
        test_cmd = [
            sys.executable, "-m", "pytest", "-x", "--tb=short"
        ] + test_targets
    elif risk in ("high", "critical"):
        test_cmd = [
            sys.executable, "-m", "pytest", "-x", "--tb=short",
            "tests/test_breakthrough/"
        ]
    else:
        # Low/medium: run just the fast harness + domain model tests
        test_cmd = [
            sys.executable, "-m", "pytest", "-x", "--tb=short",
            "tests/test_breakthrough/test_domain_models.py",
            "tests/test_breakthrough/test_implementation_harness.py",
        ]

    print(f"Running: {' '.join(test_cmd)}")
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(test_cmd, cwd=REPO_ROOT, env=env)
    if result.returncode != 0:
        all_issues.append("Test suite failed")

    if all_issues:
        print("\n── VERIFICATION FAILED ──")
        for issue in all_issues:
            print(f"  ✗ {issue}")
        return 1
    else:
        print("\n── VERIFICATION PASSED ──")
        return 0


# ── Review status ─────────────────────────────────────────────────────────

def cmd_review_status(args):
    """Check Codex review artifact status."""
    issues = _check_review_artifact_exists()
    if issues:
        print(f"FAIL: {issues[0]}")
        return 1
    issues = _check_review_no_blockers()
    if issues:
        print(f"FAIL: {issues[0]}")
        return 1
    review = json.loads(REVIEW_ARTIFACT_FILE.read_text())
    print(f"Review gate: PASS (session: {review.get('session_id', '?')})")
    warnings = review.get("warnings", [])
    if warnings:
        print(f"  Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"    - {w}")
    return 0


# ── Full gate check (pre-commit uses this) ────────────────────────────────

def cmd_gate(args):
    """Full gate check: session exists + review exists + no blockers."""
    errors: list[str] = []

    if not ACTIVE_SESSION_FILE.exists():
        errors.append("No active session artifact")
    else:
        session = json.loads(ACTIVE_SESSION_FILE.read_text())
        if session.get("commit_blocked_until_gate_pass", True):
            errors.extend(_check_review_artifact_exists())
            errors.extend(_check_review_no_blockers())

    if errors:
        print("── COMMIT GATE: BLOCKED ──")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    else:
        print("── COMMIT GATE: PASS ──")
        return 0


# ── Clean ─────────────────────────────────────────────────────────────────

def cmd_clean(args):
    """Archive active session and review artifacts."""
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    archive_dir = SESSION_DIR / "archive"
    archive_dir.mkdir(exist_ok=True)
    for f in (ACTIVE_SESSION_FILE, REVIEW_ARTIFACT_FILE):
        if f.exists():
            dest = archive_dir / f"{ts}_{f.name}"
            f.rename(dest)
            try:
                display = dest.relative_to(REPO_ROOT)
            except ValueError:
                display = dest
            print(f"Archived: {display}")
    print("Session cleaned.")
    return 0


# ── Write review artifact (helper for Codex integration) ─────────────────

def cmd_write_review(args):
    """Write a Codex review artifact from CLI flags (used by automation)."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_id = ""
    if ACTIVE_SESSION_FILE.exists():
        session_id = json.loads(ACTIVE_SESSION_FILE.read_text()).get("session_id", "")
    review = {
        "session_id": session_id,
        "reviewer": "codex",
        "reviewed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "files_reviewed": args.files or [],
        "blockers": [b.strip() for b in (args.blockers or "").split("|") if b.strip()] if args.blockers else [],
        "warnings": [w.strip() for w in (args.warnings or "").split("|") if w.strip()] if args.warnings else [],
        "suggestions": [s.strip() for s in (args.suggestions or "").split("|") if s.strip()] if args.suggestions else [],
        "gate_decision": "FAIL" if args.blockers else "PASS",
        "notes": args.notes or "",
    }
    REVIEW_ARTIFACT_FILE.write_text(json.dumps(review, indent=2) + "\n")
    try:
        display = REVIEW_ARTIFACT_FILE.relative_to(REPO_ROOT)
    except ValueError:
        display = REVIEW_ARTIFACT_FILE
    print(f"Review artifact written: {display}")
    print(f"  Gate decision: {review['gate_decision']}")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Implementation Safety Harness")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize implementation session")
    p_init.add_argument("--scope", required=True, help="Scope description")
    p_init.add_argument("--mode", default="IMPLEMENT", help="Execution mode")
    p_init.add_argument("--risk", default="low", choices=["low", "medium", "high", "critical"])
    p_init.add_argument("--files", nargs="*", help="Expected files to change")
    p_init.add_argument("--tests", nargs="*", help="Specific test targets")
    p_init.add_argument("--notes", help="Session notes")

    sub.add_parser("verify", help="Run verification gate")
    sub.add_parser("review-status", help="Check Codex review status")
    sub.add_parser("gate", help="Full commit gate check")
    sub.add_parser("clean", help="Archive and clean session artifacts")

    p_review = sub.add_parser("write-review", help="Write review artifact")
    p_review.add_argument("--files", nargs="*")
    p_review.add_argument("--blockers", help="Pipe-delimited blockers")
    p_review.add_argument("--warnings", help="Pipe-delimited warnings")
    p_review.add_argument("--suggestions", help="Pipe-delimited suggestions")
    p_review.add_argument("--notes", default="")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    dispatch = {
        "init": cmd_init,
        "verify": cmd_verify,
        "review-status": cmd_review_status,
        "gate": cmd_gate,
        "clean": cmd_clean,
        "write-review": cmd_write_review,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
