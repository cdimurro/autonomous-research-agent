"""Report generation for breakthrough runs.

Produces JSON and Markdown reports after each cycle.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .db import Repository


def _runtime_dir() -> Path:
    root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
    d = Path(root) / "breakthrough_reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_json_report(repo: Repository, run_id: str) -> dict:
    """Generate a full JSON report for a run."""
    run = repo.get_run(run_id)
    if not run:
        return {"error": f"Run {run_id} not found"}

    candidates = repo.list_candidates_for_run(run_id)
    rejections = repo.list_rejections(run_id)
    publications = []
    if run.get("publication_id"):
        pub = repo.get_publication(run["publication_id"])
        if pub:
            publications.append(pub)

    scores = {}
    for c in candidates:
        s = repo.get_score(c["id"])
        if s:
            scores[c["id"]] = s

    report = {
        "report_generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "run": run,
        "summary": {
            "candidates_generated": run.get("candidates_generated", 0),
            "candidates_rejected": run.get("candidates_rejected", 0),
            "publication_count": len(publications),
            "status": run.get("status", "unknown"),
        },
        "publications": publications,
        "rejections": rejections,
        "candidates": candidates,
        "scores": scores,
    }
    return report


def generate_markdown_report(repo: Repository, run_id: str) -> str:
    """Generate a human-readable Markdown report for a run."""
    data = generate_json_report(repo, run_id)
    if "error" in data:
        return f"# Error\n\n{data['error']}"

    run = data["run"]
    lines = [
        f"# Breakthrough Run Report",
        f"",
        f"**Run ID:** {run['id']}",
        f"**Program:** {run.get('program_name', 'unknown')}",
        f"**Mode:** {run.get('mode', 'unknown')}",
        f"**Status:** {run.get('status', 'unknown')}",
        f"**Started:** {run.get('started_at', 'N/A')}",
        f"**Completed:** {run.get('completed_at', 'N/A')}",
        f"",
        f"## Summary",
        f"",
        f"- Candidates generated: {data['summary']['candidates_generated']}",
        f"- Candidates rejected: {data['summary']['candidates_rejected']}",
        f"- Publications: {data['summary']['publication_count']}",
        f"",
    ]

    # Publication
    if data["publications"]:
        pub = data["publications"][0]
        lines.extend([
            f"## Published Candidate",
            f"",
            f"**Title:** {pub.get('candidate_title', 'N/A')}",
            f"**Status Label:** {pub.get('status_label', 'N/A')}",
            f"**Replication Priority:** {pub.get('replication_priority', 'N/A')}",
            f"",
            f"### Hypothesis",
            f"",
            f"{pub.get('hypothesis', 'N/A')}",
            f"",
            f"### Evidence Summary",
            f"",
            f"{pub.get('evidence_summary', 'N/A')}",
            f"",
            f"### Simulation Summary",
            f"",
            f"{pub.get('simulation_summary', 'N/A')}",
            f"",
            f"### Assumptions",
            f"",
        ])
        assumptions = pub.get("assumptions", "[]")
        if isinstance(assumptions, str):
            try:
                assumptions = json.loads(assumptions)
            except (json.JSONDecodeError, TypeError):
                assumptions = [assumptions]
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")

        lines.append("### Uncertainties")
        lines.append("")
        uncertainties = pub.get("uncertainties", "[]")
        if isinstance(uncertainties, str):
            try:
                uncertainties = json.loads(uncertainties)
            except (json.JSONDecodeError, TypeError):
                uncertainties = [uncertainties]
        for u in uncertainties:
            lines.append(f"- {u}")
        lines.append("")

        # Score breakdown
        score_data = pub.get("score_breakdown", "{}")
        if isinstance(score_data, str):
            try:
                score_data = json.loads(score_data)
            except (json.JSONDecodeError, TypeError):
                score_data = {}
        if score_data:
            lines.extend([
                "### Score Breakdown",
                "",
                "| Dimension | Score |",
                "|-----------|-------|",
            ])
            for k, v in score_data.items():
                if isinstance(v, float):
                    lines.append(f"| {k} | {v:.3f} |")
            lines.append("")
    else:
        lines.extend([
            "## No Publication",
            "",
            "All candidates were rejected or scored below the publication threshold.",
            "",
        ])

    # Rejections
    if data["rejections"]:
        lines.extend([
            "## Rejected Candidates",
            "",
            "| Title | Status | Reason |",
            "|-------|--------|--------|",
        ])
        for r in data["rejections"]:
            title = r.get("candidate_title", "N/A")[:40]
            status = r.get("status", "N/A")
            reason = r.get("rejection_reason", "N/A")[:60]
            lines.append(f"| {title} | {status} | {reason} |")
        lines.append("")

    return "\n".join(lines)


def save_reports(repo: Repository, run_id: str, output_dir: Optional[str] = None) -> tuple[str, str]:
    """Save JSON and Markdown reports to disk. Returns (json_path, md_path)."""
    d = Path(output_dir) if output_dir else _runtime_dir()
    d.mkdir(parents=True, exist_ok=True)

    json_data = generate_json_report(repo, run_id)
    json_path = d / f"run_{run_id}.json"
    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2, default=str)

    md_text = generate_markdown_report(repo, run_id)
    md_path = d / f"run_{run_id}.md"
    with open(md_path, "w") as f:
        f.write(md_text)

    return str(json_path), str(md_path)
