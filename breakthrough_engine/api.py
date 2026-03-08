"""Flask blueprint for Breakthrough Engine API routes.

Extends the existing Flask API with /api/breakthrough/* endpoints.
"""

from __future__ import annotations

import json
import threading

from flask import Blueprint, jsonify, request

from .config_loader import list_programs, load_program
from .db import Repository, init_db
from .orchestrator import BreakthroughOrchestrator
from .reporting import generate_json_report, generate_markdown_report, save_reports
from .review import approve_draft, reject_draft

bp = Blueprint("breakthrough", __name__, url_prefix="/api/breakthrough")

# Module-level db connection (lazy init)
_db = None
_db_path = None


def _get_db():
    global _db, _db_path
    if _db is None:
        _db = init_db(db_path=_db_path)
    return _db


def _get_repo():
    return Repository(_get_db())


def configure(db_path: str | None = None):
    """Configure the API module with a specific db path."""
    global _db_path, _db
    _db_path = db_path
    _db = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/health")
def health():
    try:
        db = _get_db()
        from .db import _current_version
        version = _current_version(db)
        return jsonify({"status": "ok", "schema_version": version})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.route("/run", methods=["POST"])
def trigger_run():
    """Trigger a breakthrough cycle. Accepts JSON body with 'program' name."""
    data = request.get_json(silent=True) or {}
    program_name = data.get("program", "general_fast_loop")

    try:
        program = load_program(program_name)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    repo = _get_repo()
    orchestrator = BreakthroughOrchestrator(program=program, repo=repo)

    # Run in background thread so API doesn't block
    def _run():
        try:
            run_record = orchestrator.run()
            save_reports(repo, run_record.id)
        except Exception:
            pass  # Error is recorded in the run record

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"status": "started", "message": f"Breakthrough cycle started for program '{program_name}'"}), 202


@bp.route("/run-sync", methods=["POST"])
def trigger_run_sync():
    """Trigger a breakthrough cycle synchronously. Returns run result."""
    data = request.get_json(silent=True) or {}
    program_name = data.get("program", "general_fast_loop")

    try:
        program = load_program(program_name)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404

    repo = _get_repo()
    orchestrator = BreakthroughOrchestrator(program=program, repo=repo)

    try:
        run_record = orchestrator.run()
        save_reports(repo, run_record.id)
        report = generate_json_report(repo, run_record.id)
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/runs")
def list_runs():
    limit = min(int(request.args.get("limit", 20)), 100)
    repo = _get_repo()
    runs = repo.list_runs(limit=limit)
    return jsonify(runs)


@bp.route("/runs/<run_id>")
def get_run(run_id: str):
    repo = _get_repo()
    run = repo.get_run(run_id)
    if not run:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)


@bp.route("/runs/<run_id>/report")
def get_run_report(run_id: str):
    """Get full JSON report for a run."""
    repo = _get_repo()
    report = generate_json_report(repo, run_id)
    if "error" in report:
        return jsonify(report), 404
    return jsonify(report)


@bp.route("/runs/<run_id>/report.md")
def get_run_report_md(run_id: str):
    """Get Markdown report for a run."""
    repo = _get_repo()
    md = generate_markdown_report(repo, run_id)
    return md, 200, {"Content-Type": "text/markdown; charset=utf-8"}


@bp.route("/publications")
def list_publications():
    limit = min(int(request.args.get("limit", 20)), 100)
    repo = _get_repo()
    pubs = repo.list_publications(limit=limit)
    return jsonify(pubs)


@bp.route("/publications/<pub_id>")
def get_publication(pub_id: str):
    repo = _get_repo()
    pub = repo.get_publication(pub_id)
    if not pub:
        return jsonify({"error": "Publication not found"}), 404
    return jsonify(pub)


@bp.route("/rejections/<run_id>")
def list_rejections(run_id: str):
    repo = _get_repo()
    rejections = repo.list_rejections(run_id)
    return jsonify(rejections)


@bp.route("/programs")
def list_programs_route():
    programs = list_programs()
    return jsonify(programs)


@bp.route("/candidates/<run_id>")
def list_candidates(run_id: str):
    repo = _get_repo()
    candidates = repo.list_candidates_for_run(run_id)
    return jsonify(candidates)


# ---------------------------------------------------------------------------
# Phase 3: Review workflow routes
# ---------------------------------------------------------------------------

@bp.route("/review/queue")
def review_queue():
    """List drafts pending review."""
    repo = _get_repo()
    drafts = repo.list_drafts(status="pending_review")
    return jsonify(drafts)


@bp.route("/review/drafts")
def list_drafts():
    """List all drafts."""
    repo = _get_repo()
    status = request.args.get("status")
    drafts = repo.list_drafts(status=status)
    return jsonify(drafts)


@bp.route("/review/drafts/<draft_id>")
def get_draft(draft_id: str):
    """Get draft details."""
    repo = _get_repo()
    draft = repo.get_draft(draft_id)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404
    events = repo.list_review_events(draft_id)
    return jsonify({"draft": draft, "review_events": events})


@bp.route("/review/drafts/<draft_id>/approve", methods=["POST"])
def approve_draft_route(draft_id: str):
    """Approve a draft and create the final publication."""
    data = request.get_json(silent=True) or {}
    reviewer = data.get("reviewer", "operator")
    notes = data.get("notes", "")
    repo = _get_repo()
    pub = approve_draft(repo, draft_id, reviewer=reviewer, notes=notes)
    if pub:
        return jsonify({"status": "approved", "publication_id": pub.id})
    return jsonify({"error": "Draft not found or already reviewed"}), 400


@bp.route("/review/drafts/<draft_id>/reject", methods=["POST"])
def reject_draft_route(draft_id: str):
    """Reject a draft."""
    data = request.get_json(silent=True) or {}
    reviewer = data.get("reviewer", "operator")
    reason = data.get("reason", "")
    repo = _get_repo()
    ok = reject_draft(repo, draft_id, reviewer=reviewer, reason=reason)
    if ok:
        return jsonify({"status": "rejected"})
    return jsonify({"error": "Draft not found or already reviewed"}), 400


# ---------------------------------------------------------------------------
# Phase 3: Metrics routes
# ---------------------------------------------------------------------------

@bp.route("/metrics/recent")
def recent_metrics():
    """Get recent run metrics."""
    repo = _get_repo()
    limit = min(int(request.args.get("limit", 10)), 50)
    metrics = repo.list_recent_metrics(limit=limit)
    return jsonify(metrics)


@bp.route("/metrics/<run_id>")
def get_metrics(run_id: str):
    """Get metrics for a specific run."""
    repo = _get_repo()
    m = repo.get_run_metrics(run_id)
    if not m:
        return jsonify({"error": "Metrics not found"}), 404
    return jsonify(m)


# ---------------------------------------------------------------------------
# Phase 3: Novelty route
# ---------------------------------------------------------------------------

@bp.route("/novelty/<candidate_id>")
def get_novelty(candidate_id: str):
    """Get novelty check for a candidate."""
    repo = _get_repo()
    n = repo.get_novelty_check(candidate_id)
    if not n:
        return jsonify({"error": "Novelty check not found"}), 404
    return jsonify(n)


# ---------------------------------------------------------------------------
# Minimal HTML views
# ---------------------------------------------------------------------------

@bp.route("/view/latest")
def view_latest():
    """Minimal HTML view of the latest publication."""
    repo = _get_repo()
    pubs = repo.list_publications(limit=1)
    if not pubs:
        return "<html><body><h1>No publications yet</h1><p>Run a breakthrough cycle first.</p></body></html>"

    pub = pubs[0]
    assumptions = pub.get("assumptions", "[]")
    if isinstance(assumptions, str):
        try:
            assumptions = json.loads(assumptions)
        except (json.JSONDecodeError, TypeError):
            assumptions = [assumptions]

    uncertainties = pub.get("uncertainties", "[]")
    if isinstance(uncertainties, str):
        try:
            uncertainties = json.loads(uncertainties)
        except (json.JSONDecodeError, TypeError):
            uncertainties = [uncertainties]

    score_data = pub.get("score_breakdown", "{}")
    if isinstance(score_data, str):
        try:
            score_data = json.loads(score_data)
        except (json.JSONDecodeError, TypeError):
            score_data = {}

    score_rows = ""
    for k, v in score_data.items():
        if isinstance(v, float):
            score_rows += f"<tr><td>{k}</td><td>{v:.3f}</td></tr>"

    assumptions_html = "".join(f"<li>{a}</li>" for a in assumptions)
    uncertainties_html = "".join(f"<li>{u}</li>" for u in uncertainties)

    return f"""<!DOCTYPE html>
<html>
<head><title>Latest Breakthrough Candidate</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; line-height: 1.6; }}
h1 {{ color: #1a5276; }}
.label {{ display: inline-block; background: #2ecc71; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.85em; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f4f4f4; }}
.section {{ margin: 1.5em 0; }}
</style>
</head>
<body>
<h1>{pub.get('candidate_title', 'N/A')}</h1>
<p><span class="label">{pub.get('status_label', 'N/A')}</span>
   Published: {pub.get('publication_date', 'N/A')} |
   Replication Priority: {pub.get('replication_priority', 'N/A')}</p>

<div class="section">
<h2>Hypothesis</h2>
<p>{pub.get('hypothesis', 'N/A')}</p>
</div>

<div class="section">
<h2>Evidence Summary</h2>
<pre>{pub.get('evidence_summary', 'N/A')}</pre>
</div>

<div class="section">
<h2>Simulation Summary</h2>
<p>{pub.get('simulation_summary', 'N/A')}</p>
</div>

<div class="section">
<h2>Assumptions</h2>
<ul>{assumptions_html or '<li>None disclosed</li>'}</ul>
</div>

<div class="section">
<h2>Uncertainties</h2>
<ul>{uncertainties_html or '<li>None disclosed</li>'}</ul>
</div>

<div class="section">
<h2>Score Breakdown</h2>
<table><tr><th>Dimension</th><th>Score</th></tr>{score_rows}</table>
</div>

<p><a href="/api/breakthrough/publications">All Publications (JSON)</a> |
   <a href="/api/breakthrough/runs">All Runs (JSON)</a></p>
</body>
</html>"""


@bp.route("/view/runs")
def view_runs():
    """Minimal HTML view of recent runs."""
    repo = _get_repo()
    runs = repo.list_runs(limit=20)

    rows = ""
    for r in runs:
        run_id = r.get("id", "")
        rows += f"""<tr>
            <td><a href="/api/breakthrough/runs/{run_id}">{run_id[:12]}...</a></td>
            <td>{r.get('program_name', 'N/A')}</td>
            <td>{r.get('status', 'N/A')}</td>
            <td>{r.get('candidates_generated', 0)}</td>
            <td>{r.get('started_at', 'N/A')}</td>
            <td><a href="/api/breakthrough/runs/{run_id}/report.md">Report</a></td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><title>Breakthrough Runs</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f4f4f4; }}
</style>
</head>
<body>
<h1>Breakthrough Engine - Recent Runs</h1>
<table>
<tr><th>Run ID</th><th>Program</th><th>Status</th><th>Candidates</th><th>Started</th><th>Report</th></tr>
{rows}
</table>
<p><a href="/api/breakthrough/view/latest">Latest Publication</a></p>
</body>
</html>"""
