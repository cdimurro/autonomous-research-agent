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
    # Support both JSON API and HTML form submission
    reviewer = data.get("reviewer") or request.form.get("reviewer", "operator")
    notes = data.get("notes") or request.form.get("notes", "")
    repo = _get_repo()
    pub = approve_draft(repo, draft_id, reviewer=reviewer, notes=notes)

    # If request came from HTML form, redirect back to review queue
    if request.content_type and "json" in request.content_type:
        if pub:
            return jsonify({"status": "approved", "publication_id": pub.id})
        return jsonify({"error": "Draft not found or already reviewed"}), 400

    # HTML response for form submissions
    if pub:
        return _review_result_page(
            "Draft Approved",
            f"Draft {draft_id[:12]} approved. Publication {pub.id[:12]} created.",
            success=True,
        )
    return _review_result_page(
        "Approval Failed",
        f"Draft {draft_id[:12]} not found or already reviewed.",
        success=False,
    ), 400


@bp.route("/review/drafts/<draft_id>/reject", methods=["POST"])
def reject_draft_route(draft_id: str):
    """Reject a draft."""
    data = request.get_json(silent=True) or {}
    reviewer = data.get("reviewer") or request.form.get("reviewer", "operator")
    reason = data.get("reason") or request.form.get("reason", "")
    repo = _get_repo()
    ok = reject_draft(repo, draft_id, reviewer=reviewer, reason=reason)

    if request.content_type and "json" in request.content_type:
        if ok:
            return jsonify({"status": "rejected"})
        return jsonify({"error": "Draft not found or already reviewed"}), 400

    if ok:
        return _review_result_page(
            "Draft Rejected",
            f"Draft {draft_id[:12]} rejected." + (f" Reason: {reason}" if reason else ""),
            success=True,
        )
    return _review_result_page(
        "Rejection Failed",
        f"Draft {draft_id[:12]} not found or already reviewed.",
        success=False,
    ), 400


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

def _review_result_page(title: str, message: str, success: bool = True) -> str:
    """Minimal HTML result page for review actions."""
    color = "#27ae60" if success else "#e74c3c"
    icon = "+" if success else "X"
    return f"""<!DOCTYPE html>
<html><head><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 4em auto; padding: 0 1em; text-align: center; }}
.result {{ border: 2px solid {color}; border-radius: 8px; padding: 2em; margin: 2em 0; }}
.result h2 {{ color: {color}; }}
</style></head>
<body>
<div class="result">
<h2>[{icon}] {title}</h2>
<p>{message}</p>
</div>
<p><a href="/api/breakthrough/view/review">Back to Review Queue</a> |
   <a href="/api/breakthrough/view/runs">All Runs</a></p>
</body></html>"""


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
<p><a href="/api/breakthrough/view/latest">Latest Publication</a> |
   <a href="/api/breakthrough/view/review">Review Queue</a></p>
</body>
</html>"""


@bp.route("/view/review")
def view_review():
    """Phase 4B: Minimal operator review HTML view with trust signals."""
    repo = _get_repo()
    drafts = repo.list_drafts(status="pending_review")

    if not drafts:
        return """<!DOCTYPE html><html><head><title>Review Queue</title>
<style>body { font-family: system-ui, sans-serif; max-width: 800px; margin: 2em auto; padding: 0 1em; }</style>
</head><body><h1>Review Queue</h1><p>No drafts pending review.</p>
<p><a href="/api/breakthrough/view/runs">All Runs</a></p></body></html>"""

    cards = ""
    for d in drafts:
        draft_id = d.get("id", "")
        candidate_id = d.get("candidate_id", "")

        # Gather trust signals
        novelty = repo.get_novelty_check(candidate_id)
        score_data = d.get("score_breakdown", "{}")
        if isinstance(score_data, str):
            try:
                score_data = json.loads(score_data)
            except (json.JSONDecodeError, TypeError):
                score_data = {}

        # Domain fit
        domain_fit = repo.get_domain_fit(candidate_id)
        df_score = "N/A"
        df_keywords = ""
        if domain_fit:
            df_score = f"{domain_fit.get('domain_fit_score', 0):.2f}"
            kw_raw = domain_fit.get("matched_keywords", "[]")
            if isinstance(kw_raw, str):
                try:
                    kw_list = json.loads(kw_raw)
                except (json.JSONDecodeError, TypeError):
                    kw_list = []
            else:
                kw_list = kw_raw or []
            df_keywords = ", ".join(kw_list[:5]) if kw_list else "none"

        # Embedding novelty
        emb_nov = repo.get_embedding_novelty(candidate_id)
        emb_sim = "N/A"
        emb_basis = "N/A"
        if emb_nov:
            emb_sim = f"{emb_nov.get('embedding_similarity_max', 0):.3f}"
            emb_basis = emb_nov.get("novelty_basis", "N/A")

        # Novelty summary
        nov_decision = "N/A"
        nov_score = "N/A"
        if novelty:
            nov_decision = novelty.get("decision", "N/A")
            nov_score = f"{novelty.get('novelty_score', 0):.2f}"

        # Gate diagnostics
        gate_diags = repo.list_gate_diagnostics(d.get("run_id", ""))
        gate_rows = ""
        for gd in gate_diags:
            if gd.get("candidate_id") == candidate_id:
                icon = "+" if gd.get("passed") else "X"
                reasons_raw = gd.get("reasons", "[]")
                if isinstance(reasons_raw, str):
                    try:
                        reasons_list = json.loads(reasons_raw)
                    except (json.JSONDecodeError, TypeError):
                        reasons_list = [reasons_raw]
                else:
                    reasons_list = reasons_raw or []
                gate_rows += f"<tr><td>[{icon}] {gd.get('gate_name', '')}</td><td>{gd.get('score', 0):.2f}</td><td>{'; '.join(str(r) for r in reasons_list[:3])}</td></tr>"

        # Score rows
        score_rows = ""
        for k, v in score_data.items():
            if isinstance(v, float):
                score_rows += f"<tr><td>{k}</td><td>{v:.3f}</td></tr>"

        assumptions_raw = d.get("assumptions", "[]")
        if isinstance(assumptions_raw, str):
            try:
                assumptions = json.loads(assumptions_raw)
            except (json.JSONDecodeError, TypeError):
                assumptions = []
        else:
            assumptions = assumptions_raw or []
        assumptions_html = "".join(f"<li>{a}</li>" for a in assumptions)

        cards += f"""
<div class="card">
  <h2>{d.get('candidate_title', 'N/A')}</h2>
  <p class="meta">Draft: {draft_id[:12]} | Run: {d.get('run_id', '')[:12]} | Priority: {d.get('replication_priority', 'N/A')}</p>

  <h3>Hypothesis</h3>
  <p>{d.get('hypothesis', 'N/A')[:500]}</p>

  <h3>Evidence</h3>
  <pre>{d.get('evidence_summary', 'N/A')[:500]}</pre>

  <h3>Trust Signals</h3>
  <table>
    <tr><th>Signal</th><th>Value</th></tr>
    <tr><td>Novelty decision</td><td>{nov_decision}</td></tr>
    <tr><td>Novelty score</td><td>{nov_score}</td></tr>
    <tr><td>Embedding similarity (max)</td><td>{emb_sim}</td></tr>
    <tr><td>Embedding basis</td><td>{emb_basis}</td></tr>
    <tr><td>Domain-fit score</td><td>{df_score}</td></tr>
    <tr><td>Domain keywords</td><td>{df_keywords}</td></tr>
  </table>

  {"<h3>Gate Diagnostics</h3><table><tr><th>Gate</th><th>Score</th><th>Details</th></tr>" + gate_rows + "</table>" if gate_rows else ""}

  {"<h3>Score Breakdown</h3><table><tr><th>Dimension</th><th>Score</th></tr>" + score_rows + "</table>" if score_rows else ""}

  <h3>Assumptions</h3>
  <ul>{assumptions_html or '<li>None</li>'}</ul>

  <p>{d.get('novelty_summary', '')}</p>

  <div class="actions">
    <form method="POST" action="/api/breakthrough/review/drafts/{draft_id}/approve" style="display:inline"
          onsubmit="return confirm('Approve this draft for publication?')">
      <input type="hidden" name="reviewer" value="operator">
      <input type="text" name="notes" placeholder="Notes (optional)" style="padding:6px;border:1px solid #ccc;border-radius:4px;width:200px;margin-right:4px">
      <button type="submit" class="btn-approve">Approve</button>
    </form>
    <form method="POST" action="/api/breakthrough/review/drafts/{draft_id}/reject" style="display:inline"
          onsubmit="return confirm('Reject this draft?')">
      <input type="hidden" name="reviewer" value="operator">
      <input type="text" name="reason" placeholder="Rejection reason" style="padding:6px;border:1px solid #ccc;border-radius:4px;width:200px;margin-right:4px">
      <button type="submit" class="btn-reject">Reject</button>
    </form>
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html>
<head><title>Operator Review Queue</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; line-height: 1.5; }}
h1 {{ color: #1a5276; }}
.card {{ border: 1px solid #ddd; border-radius: 8px; padding: 1.5em; margin: 1.5em 0; background: #fafafa; }}
.meta {{ color: #777; font-size: 0.9em; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.5em 0; }}
th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 0.9em; }}
th {{ background: #f0f0f0; }}
pre {{ background: #f8f8f8; padding: 0.8em; border-radius: 4px; white-space: pre-wrap; font-size: 0.85em; }}
.btn-approve {{ background: #27ae60; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }}
.btn-reject {{ background: #e74c3c; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-left: 8px; }}
.actions {{ margin-top: 1em; }}
</style>
</head>
<body>
<h1>Operator Review Queue</h1>
<p>{len(drafts)} draft(s) pending review</p>
{cards}
<p><a href="/api/breakthrough/view/runs">All Runs</a> | <a href="/api/breakthrough/view/latest">Latest Publication</a></p>
</body>
</html>"""


@bp.route("/view/candidate/<candidate_id>")
def view_candidate(candidate_id: str):
    """Candidate detail view with all trust signals (JSON + HTML)."""
    repo = _get_repo()
    candidate = repo.get_candidate(candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found"}), 404

    score = repo.get_score(candidate_id)
    novelty = repo.get_novelty_check(candidate_id)
    domain_fit = repo.get_domain_fit(candidate_id)
    emb_novelty = repo.get_embedding_novelty(candidate_id)
    rankings = repo.list_evidence_rankings(candidate_id)

    # If JSON requested, return JSON
    if request.accept_mimetypes.best == "application/json":
        return jsonify({
            "candidate": candidate,
            "score": score,
            "novelty": novelty,
            "domain_fit": domain_fit,
            "embedding_novelty": emb_novelty,
            "evidence_rankings": rankings,
        })

    # HTML detail view
    return _candidate_detail_html(candidate, score, novelty, domain_fit, emb_novelty, rankings)


@bp.route("/view/embedding-drift")
def view_embedding_drift():
    """Embedding drift report across recent runs."""
    from .embedding_monitor import EmbeddingMonitor
    repo = _get_repo()
    monitor = EmbeddingMonitor(repo)
    report = monitor.get_drift_report(limit=20)
    return jsonify(report)


@bp.route("/view/calibration/<run_id>")
def view_calibration(run_id: str):
    """Calibration diagnostics for a specific run."""
    repo = _get_repo()
    cal = repo.get_calibration_diagnostic(run_id)
    if not cal:
        return jsonify({"error": "No calibration data for this run"}), 404
    return jsonify(cal)


@bp.route("/view/thresholds")
def view_thresholds():
    """Current active thresholds for all gates."""
    return jsonify({
        "publication_threshold": 0.60,
        "novelty_lexical_exact_title": 0.95,
        "novelty_lexical_statement_overlap": 0.80,
        "novelty_lexical_mechanism_overlap": 0.75,
        "novelty_lexical_keyword_warn": 0.60,
        "novelty_embedding_block": 0.88,
        "novelty_embedding_warn": 0.78,
        "domain_fit_min_score": 0.25,
        "evidence_strength_floor": 0.30,
        "mechanism_specificity_min_chars": 50,
        "novelty_score_floor": 0.30,
    })


def _candidate_detail_html(candidate, score, novelty, domain_fit, emb_novelty, rankings):
    """Render candidate detail as HTML with all trust signals."""
    c = candidate

    # Score table
    score_rows = ""
    if score:
        for k in ["novelty_score", "plausibility_score", "impact_score",
                   "evidence_strength_score", "simulation_readiness_score",
                   "validation_cost_score", "final_score"]:
            v = score.get(k, 0)
            if isinstance(v, (int, float)):
                label = k.replace("_score", "").replace("_", " ").title()
                bar_w = int(v * 100)
                score_rows += f'<tr><td>{label}</td><td>{v:.3f}</td><td><div class="bar" style="width:{bar_w}%"></div></td></tr>'

    # Novelty info
    nov_html = "<p>Not evaluated</p>"
    if novelty:
        nov_html = f"""<table>
        <tr><td>Decision</td><td>{novelty.get('decision', 'N/A')}</td></tr>
        <tr><td>Score</td><td>{novelty.get('novelty_score', 0):.3f}</td></tr>
        <tr><td>Explanation</td><td>{(novelty.get('explanation', '') or '')[:300]}</td></tr>
        </table>"""

    # Embedding novelty
    emb_html = "<p>Not evaluated</p>"
    if emb_novelty:
        nn_raw = emb_novelty.get("nearest_neighbors", "[]")
        if isinstance(nn_raw, str):
            try:
                nns = json.loads(nn_raw)
            except (json.JSONDecodeError, TypeError):
                nns = []
        else:
            nns = nn_raw or []
        nn_rows = ""
        for nn in nns[:5]:
            nn_rows += f'<tr><td>{nn.get("title", "")[:80]}</td><td>{nn.get("similarity", 0):.3f}</td><td>{nn.get("source", "")}</td></tr>'

        emb_html = f"""<table>
        <tr><td>Max similarity</td><td>{emb_novelty.get('embedding_similarity_max', 0):.4f}</td></tr>
        <tr><td>Basis</td><td>{emb_novelty.get('novelty_basis', 'N/A')}</td></tr>
        <tr><td>Blocked</td><td>{'Yes' if emb_novelty.get('blocked_by_prior_art') else 'No'}</td></tr>
        </table>"""
        if nn_rows:
            emb_html += f"""<h4>Nearest Neighbors</h4>
            <table><tr><th>Title</th><th>Similarity</th><th>Source</th></tr>{nn_rows}</table>"""

    # Domain fit
    df_html = "<p>Not evaluated</p>"
    if domain_fit:
        kw_raw = domain_fit.get("matched_keywords", "[]")
        if isinstance(kw_raw, str):
            try:
                kw_list = json.loads(kw_raw)
            except (json.JSONDecodeError, TypeError):
                kw_list = []
        else:
            kw_list = kw_raw or []
        df_html = f"""<table>
        <tr><td>Score</td><td>{domain_fit.get('domain_fit_score', 0):.3f}</td></tr>
        <tr><td>Domain</td><td>{domain_fit.get('domain', 'N/A')}</td></tr>
        <tr><td>Passed</td><td>{'Yes' if domain_fit.get('passed') else 'No'}</td></tr>
        <tr><td>Keywords</td><td>{', '.join(kw_list[:8])}</td></tr>
        </table>"""

    # Evidence rankings
    rank_html = ""
    if rankings:
        rank_rows = ""
        for r in rankings[:5]:
            rank_rows += f'<tr><td>{r.get("evidence_id", "")[:16]}</td><td>{r.get("composite_score", 0):.3f}</td><td>{r.get("rank_explanation", "")[:80]}</td></tr>'
        rank_html = f"""<h3>Evidence Rankings</h3>
        <table><tr><th>Evidence ID</th><th>Score</th><th>Explanation</th></tr>{rank_rows}</table>"""

    return f"""<!DOCTYPE html>
<html><head><title>Candidate: {c.get('title', 'N/A')[:60]}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; line-height: 1.5; }}
h1 {{ color: #1a5276; font-size: 1.3em; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.5em 0; }}
th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 0.9em; }}
th {{ background: #f0f0f0; }}
pre {{ background: #f8f8f8; padding: 0.8em; border-radius: 4px; white-space: pre-wrap; font-size: 0.85em; }}
.bar {{ background: #3498db; height: 14px; border-radius: 3px; }}
.section {{ margin: 1.5em 0; }}
.status {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.85em;
           background: {'#27ae60' if c.get('status') == 'published' else '#e67e22' if 'pending' in str(c.get('status', '')) else '#95a5a6'}; color: white; }}
</style></head>
<body>
<h1>{c.get('title', 'N/A')}</h1>
<p><span class="status">{c.get('status', 'N/A')}</span> | Domain: {c.get('domain', 'N/A')} | Run: {c.get('run_id', '')[:12]}</p>

<div class="section"><h3>Statement</h3><p>{c.get('statement', 'N/A')}</p></div>
<div class="section"><h3>Mechanism</h3><pre>{c.get('mechanism', 'N/A')}</pre></div>

<div class="section"><h3>Score Breakdown</h3>
<table><tr><th>Dimension</th><th>Score</th><th>Bar</th></tr>{score_rows}</table></div>

<div class="section"><h3>Lexical Novelty</h3>{nov_html}</div>
<div class="section"><h3>Embedding Novelty</h3>{emb_html}</div>
<div class="section"><h3>Domain Fit</h3>{df_html}</div>
{rank_html}

<p><a href="/api/breakthrough/view/review">Review Queue</a> |
   <a href="/api/breakthrough/view/runs">All Runs</a></p>
</body></html>"""
