"""Evaluation Pack Exporter for Breakthrough Engine campaigns.

Phase 7B: Generates rich, analysis-ready evaluation packs from completed
campaigns. Captures all candidate data, scores, finalists, falsification
summaries, posteriors, evidence refs, and metadata in a normalized format
optimized for external analysis (e.g., ChatGPT, spreadsheets).

Output structure:
  runtime/evaluation_packs/<campaign_id>/
    evaluation_pack.json       # Complete structured pack
    evaluation_pack.md         # Markdown summary for humans
    candidates.csv             # All candidates (CSV for spreadsheet analysis)
    finalists.csv              # Finalist rows with all score dimensions
    posteriors.csv             # Bayesian posteriors snapshot (if available)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Analysis Schema Version
# ---------------------------------------------------------------------------

ANALYSIS_SCHEMA_VERSION = "v001"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CandidateRecord:
    candidate_id: str
    run_id: str
    title: str
    domain: str
    statement: str
    mechanism: str
    expected_outcome: str
    testability_window_hours: float
    novelty_notes: str
    assumptions: list[str]
    risk_flags: list[str]
    evidence_refs: list[str]
    status: str
    created_at: str
    # Scores
    final_score: Optional[float] = None
    novelty_score: Optional[float] = None
    plausibility_score: Optional[float] = None
    impact_score: Optional[float] = None
    validation_cost_score: Optional[float] = None
    evidence_strength_score: Optional[float] = None
    simulation_readiness_score: Optional[float] = None
    # Falsification
    falsification_risk: Optional[str] = None
    falsification_passed: Optional[bool] = None
    assumption_fragility_score: Optional[float] = None
    falsification_reasoning: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "title": self.title,
            "domain": self.domain,
            "statement": self.statement,
            "mechanism": self.mechanism,
            "expected_outcome": self.expected_outcome,
            "testability_window_hours": self.testability_window_hours,
            "novelty_notes": self.novelty_notes,
            "assumptions": self.assumptions,
            "risk_flags": self.risk_flags,
            "evidence_refs": self.evidence_refs,
            "status": self.status,
            "created_at": self.created_at,
            "scores": {
                "final": self.final_score,
                "novelty": self.novelty_score,
                "plausibility": self.plausibility_score,
                "impact": self.impact_score,
                "validation_cost": self.validation_cost_score,
                "evidence_strength": self.evidence_strength_score,
                "simulation_readiness": self.simulation_readiness_score,
            },
            "falsification": {
                "risk": self.falsification_risk,
                "passed": self.falsification_passed,
                "assumption_fragility_score": self.assumption_fragility_score,
                "reasoning": self.falsification_reasoning,
            },
        }

    def to_csv_row(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "run_id": self.run_id,
            "title": self.title,
            "domain": self.domain,
            "status": self.status,
            "final_score": self.final_score,
            "novelty_score": self.novelty_score,
            "plausibility_score": self.plausibility_score,
            "impact_score": self.impact_score,
            "validation_cost_score": self.validation_cost_score,
            "evidence_strength_score": self.evidence_strength_score,
            "simulation_readiness_score": self.simulation_readiness_score,
            "falsification_risk": self.falsification_risk,
            "falsification_passed": self.falsification_passed,
            "assumption_fragility_score": self.assumption_fragility_score,
            "testability_window_hours": self.testability_window_hours,
            "evidence_refs": "|".join(self.evidence_refs),
            "created_at": self.created_at,
        }


@dataclass
class EvaluationPack:
    """Complete analysis-ready evaluation pack for one campaign."""

    schema_version: str = ANALYSIS_SCHEMA_VERSION
    campaign_id: str = ""
    daily_campaign_id: str = ""
    profile_name: str = ""
    profile_type: str = ""
    status: str = ""
    started_at: str = ""
    completed_at: str = ""
    elapsed_seconds: float = 0.0

    # Config
    domain: str = ""
    program_name: str = ""
    mode: str = ""
    wall_clock_budget_minutes: int = 0
    candidate_trial_budget: int = 0

    # Models
    generation_model: str = ""
    embedding_provider: str = ""
    embedding_model: str = ""
    policy_used: str = ""

    # Counts
    total_candidates_generated: int = 0
    total_candidates_blocked: int = 0
    total_shortlisted: int = 0
    total_finalists: int = 0
    total_runs: int = 0

    # Champion
    champion_id: str = ""
    champion_title: str = ""
    champion_rationale: str = ""

    # Stage events
    stage_events: list[dict] = field(default_factory=list)

    # Preflight
    preflight_readiness_score: float = 0.0
    preflight_pass_count: int = 0
    preflight_warn_count: int = 0
    preflight_fail_count: int = 0

    # Candidates
    all_candidates: list[CandidateRecord] = field(default_factory=list)

    # Posteriors
    posteriors: list[dict] = field(default_factory=list)

    # Runs
    runs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        finalists = [c for c in self.all_candidates if c.status == "finalist"]
        champion = next((c for c in finalists if c.candidate_id == self.champion_id), None)

        # Tie-break rationale
        tie_notes = _build_tiebreak_notes(finalists, self.champion_id)

        return {
            "schema_version": self.schema_version,
            "campaign": {
                "campaign_id": self.campaign_id,
                "daily_campaign_id": self.daily_campaign_id,
                "profile_name": self.profile_name,
                "profile_type": self.profile_type,
                "status": self.status,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "elapsed_seconds": self.elapsed_seconds,
            },
            "config": {
                "domain": self.domain,
                "program_name": self.program_name,
                "mode": self.mode,
                "wall_clock_budget_minutes": self.wall_clock_budget_minutes,
                "candidate_trial_budget": self.candidate_trial_budget,
            },
            "models": {
                "generation_model": self.generation_model,
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model,
                "policy_used": self.policy_used,
            },
            "statistics": {
                "total_candidates_generated": self.total_candidates_generated,
                "total_candidates_blocked": self.total_candidates_blocked,
                "total_shortlisted": self.total_shortlisted,
                "total_finalists": self.total_finalists,
                "total_runs": self.total_runs,
            },
            "champion": champion.to_dict() if champion else {},
            "champion_rationale": self.champion_rationale,
            "tiebreak_notes": tie_notes,
            "preflight": {
                "readiness_score": self.preflight_readiness_score,
                "pass_count": self.preflight_pass_count,
                "warn_count": self.preflight_warn_count,
                "fail_count": self.preflight_fail_count,
            },
            "stage_events": self.stage_events,
            "finalists": [c.to_dict() for c in finalists],
            "all_candidates": [c.to_dict() for c in self.all_candidates],
            "runs": self.runs,
            "posteriors": self.posteriors,
        }


def _build_tiebreak_notes(finalists: list[CandidateRecord], champion_id: str) -> dict:
    """Explain ranking and tie-break decisions."""
    if not finalists:
        return {}

    sorted_f = sorted(
        finalists,
        key=lambda c: (c.final_score or 0.0, c.simulation_readiness_score or 0.0),
        reverse=True,
    )

    ranking = []
    for rank, c in enumerate(sorted_f, 1):
        is_champion = c.candidate_id == champion_id
        ranking.append({
            "rank": rank,
            "candidate_id": c.candidate_id,
            "title": c.title,
            "final_score": c.final_score,
            "is_champion": is_champion,
            "why_ranked_here": _explain_rank(c, sorted_f, rank, champion_id),
        })

    return {
        "ranked_finalists": ranking,
        "tiebreak_dimension": "simulation_readiness_score (secondary sort on ties)",
        "selection_basis": "highest final_score with simulation_readiness_score as tiebreak",
    }


def _explain_rank(
    c: CandidateRecord,
    sorted_finalists: list[CandidateRecord],
    rank: int,
    champion_id: str,
) -> str:
    if c.candidate_id == champion_id:
        above = [f for f in sorted_finalists[:rank - 1] if f.final_score == c.final_score]
        if above:
            return (
                f"Tied on final_score={c.final_score:.3f}. "
                f"Selected as champion due to higher simulation_readiness_score={c.simulation_readiness_score}."
            )
        return f"Highest final_score={c.final_score:.3f}. Selected as champion."

    champion = next((f for f in sorted_finalists if f.candidate_id == champion_id), None)
    if champion and c.final_score == champion.final_score:
        return (
            f"Tied on final_score={c.final_score:.3f} with champion. "
            f"Lower simulation_readiness_score={c.simulation_readiness_score} vs "
            f"champion's {champion.simulation_readiness_score}."
        )
    if champion:
        return f"Score {c.final_score:.3f} < champion {champion.final_score:.3f}."
    return f"Score {c.final_score:.3f}."


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------

class EvaluationPackExporter:
    """Exports a full evaluation pack for a completed campaign."""

    def __init__(self, db_path: Optional[str] = None):
        runtime_root = os.environ.get("SCIRES_RUNTIME_ROOT", "runtime")
        self.db_path = db_path or os.path.join(runtime_root, "db", "scires.db")
        self.runtime_root = runtime_root

    def export(self, campaign_id: str, overwrite: bool = False) -> str:
        """Export evaluation pack. Returns output directory path."""
        out_dir = os.path.join(self.runtime_root, "evaluation_packs", campaign_id)
        if os.path.exists(out_dir) and not overwrite:
            logger.info("Evaluation pack already exists at %s", out_dir)
            return out_dir

        os.makedirs(out_dir, exist_ok=True)
        pack = self._build_pack(campaign_id)
        self._write_json(pack, out_dir)
        self._write_markdown(pack, out_dir)
        self._write_candidates_csv(pack, out_dir)
        self._write_finalists_csv(pack, out_dir)
        self._write_posteriors_csv(pack, out_dir)
        self._record_in_db(campaign_id, out_dir, pack)

        logger.info("Evaluation pack exported to %s", out_dir)
        return out_dir

    def _build_pack(self, campaign_id: str) -> EvaluationPack:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        pack = EvaluationPack(campaign_id=campaign_id)

        # --- Campaign receipt ---
        cur.execute(
            "SELECT * FROM bt_campaign_receipts WHERE campaign_id = ?", (campaign_id,)
        )
        receipt = cur.fetchone()
        if receipt:
            config = json.loads(receipt["config_json"] or "{}")
            preflight = json.loads(receipt["preflight_json"] or "{}")
            stage_events = json.loads(receipt["stage_events_json"] or "[]")

            pack.profile_name = receipt["profile_name"]
            pack.profile_type = receipt["profile_type"]
            pack.status = receipt["status"]
            pack.started_at = receipt["started_at"]
            pack.completed_at = receipt["completed_at"] or ""
            pack.champion_id = receipt["champion_candidate_id"] or ""
            pack.champion_title = receipt["champion_candidate_title"] or ""
            pack.total_candidates_generated = receipt["total_candidates_generated"] or 0
            pack.total_candidates_blocked = receipt["total_blocked"] or 0
            pack.total_shortlisted = receipt["total_shortlisted"] or 0

            pack.domain = config.get("domain", "")
            pack.program_name = config.get("program_name", "")
            pack.mode = config.get("mode", "")
            pack.wall_clock_budget_minutes = config.get("wall_clock_budget_minutes", 0)
            pack.candidate_trial_budget = config.get("candidate_trial_budget", 0)

            pack.embedding_provider = config.get("embedding_provider", "MockEmbeddingProvider")
            pack.embedding_model = config.get("embedding_model", "mock")

            pack.preflight_readiness_score = preflight.get("readiness_score", 0.0)
            pack.preflight_pass_count = preflight.get("pass_count", 0)
            pack.preflight_warn_count = preflight.get("warn_count", 0)
            pack.preflight_fail_count = preflight.get("fail_count", 0)
            pack.stage_events = stage_events

        # --- Daily campaign (gets elapsed, rationale, daily_campaign_id) ---
        cur.execute(
            "SELECT * FROM bt_daily_campaigns WHERE campaign_id = ?", (campaign_id,)
        )
        dc = cur.fetchone()
        if dc:
            pack.daily_campaign_id = dc["campaign_id"] if "campaign_id" in dc.keys() else ""
            pack.daily_campaign_id = dc["id"] if "id" in dc.keys() else pack.daily_campaign_id
            result = json.loads(dc["result_json"] or "{}")
            pack.policy_used = result.get("policy_used", dc["policy_id"] if "policy_id" in dc.keys() else "")
            pack.champion_rationale = result.get("champion_selection_rationale", "")
            elapsed = result.get("elapsed_seconds", 0.0)
            pack.elapsed_seconds = elapsed

        # --- Model info from environment / defaults ---
        pack.generation_model = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b-q4_K_M")

        # --- Runs for this campaign ---
        # We match by started_at window using campaign timestamps
        if pack.started_at:
            cur.execute(
                """SELECT id, program_name, mode, status, candidates_generated,
                          candidates_rejected, started_at, completed_at
                   FROM bt_runs
                   WHERE started_at >= ? AND started_at <= ?
                   ORDER BY started_at""",
                (pack.started_at, pack.completed_at or "9999"),
            )
            runs = cur.fetchall()
            pack.runs = [dict(r) for r in runs]
            pack.total_runs = len(runs)
            run_ids = [r["id"] for r in runs]
        else:
            run_ids = []

        # --- Candidates ---
        if run_ids:
            placeholders = ",".join("?" * len(run_ids))
            cur.execute(
                f"""SELECT c.*, s.final_score, s.novelty_score, s.plausibility_score,
                           s.impact_score, s.validation_cost_score,
                           s.evidence_strength_score, s.simulation_readiness_score
                    FROM bt_candidates c
                    LEFT JOIN bt_scores s ON s.candidate_id = c.id
                    WHERE c.run_id IN ({placeholders})
                    ORDER BY s.final_score DESC NULLS LAST, c.created_at""",
                run_ids,
            )
            rows = cur.fetchall()

            # Build falsification lookup
            cand_ids = [r["id"] for r in rows] if rows else ["__none__"]
            cand_placeholders = ",".join("?" * len(cand_ids))
            cur.execute(
                f"""SELECT candidate_id, falsification_risk, passed,
                           assumption_fragility_score, reasoning
                    FROM bt_falsification_summaries
                    WHERE candidate_id IN ({cand_placeholders})""",
                cand_ids,
            )
            falsif = {r["candidate_id"]: dict(r) for r in cur.fetchall()}

            candidates = []
            for row in rows:
                cid = row["id"]
                try:
                    assumptions = json.loads(row["assumptions"] or "[]")
                except Exception:
                    assumptions = []
                try:
                    risk_flags = json.loads(row["risk_flags"] or "[]")
                except Exception:
                    risk_flags = []
                try:
                    evidence_refs = json.loads(row["evidence_refs"] or "[]")
                except Exception:
                    evidence_refs = []

                f = falsif.get(cid, {})
                rec = CandidateRecord(
                    candidate_id=cid,
                    run_id=row["run_id"],
                    title=row["title"] or "",
                    domain=row["domain"] or "",
                    statement=row["statement"] or "",
                    mechanism=row["mechanism"] or "",
                    expected_outcome=row["expected_outcome"] or "",
                    testability_window_hours=row["testability_window_hours"] or 0.0,
                    novelty_notes=row["novelty_notes"] or "",
                    assumptions=assumptions,
                    risk_flags=risk_flags,
                    evidence_refs=evidence_refs,
                    status=row["status"] or "",
                    created_at=row["created_at"] or "",
                    final_score=row["final_score"],
                    novelty_score=row["novelty_score"],
                    plausibility_score=row["plausibility_score"],
                    impact_score=row["impact_score"],
                    validation_cost_score=row["validation_cost_score"],
                    evidence_strength_score=row["evidence_strength_score"],
                    simulation_readiness_score=row["simulation_readiness_score"],
                    falsification_risk=f.get("falsification_risk"),
                    falsification_passed=bool(f.get("passed")) if f else None,
                    assumption_fragility_score=f.get("assumption_fragility_score"),
                    falsification_reasoning=f.get("reasoning"),
                )
                candidates.append(rec)

            pack.all_candidates = candidates
            pack.total_finalists = sum(1 for c in candidates if c.status == "finalist")

        # --- Posteriors ---
        cur.execute(
            """SELECT policy_id, domain, metric_name, distribution_type,
                      alpha, beta, mu, M2, n, last_updated
               FROM bt_bayesian_posteriors
               WHERE policy_id = ?
               ORDER BY metric_name""",
            (pack.policy_used or "phase5_champion",),
        )
        pack.posteriors = [dict(r) for r in cur.fetchall()]

        conn.close()
        return pack

    def _write_json(self, pack: EvaluationPack, out_dir: str) -> None:
        path = os.path.join(out_dir, "evaluation_pack.json")
        with open(path, "w") as f:
            json.dump(pack.to_dict(), f, indent=2, default=str)
        logger.info("Wrote %s", path)

    def _write_markdown(self, pack: EvaluationPack, out_dir: str) -> None:
        path = os.path.join(out_dir, "evaluation_pack.md")
        md = _render_markdown(pack)
        with open(path, "w") as f:
            f.write(md)
        logger.info("Wrote %s", path)

    def _write_candidates_csv(self, pack: EvaluationPack, out_dir: str) -> None:
        if not pack.all_candidates:
            return
        path = os.path.join(out_dir, "candidates.csv")
        fieldnames = list(pack.all_candidates[0].to_csv_row().keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for c in pack.all_candidates:
                writer.writerow(c.to_csv_row())
        logger.info("Wrote %s (%d rows)", path, len(pack.all_candidates))

    def _write_finalists_csv(self, pack: EvaluationPack, out_dir: str) -> None:
        finalists = [c for c in pack.all_candidates if c.status == "finalist"]
        if not finalists:
            return
        path = os.path.join(out_dir, "finalists.csv")
        fieldnames = list(finalists[0].to_csv_row().keys()) + ["statement", "mechanism"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for c in finalists:
                row = c.to_csv_row()
                row["statement"] = c.statement
                row["mechanism"] = c.mechanism
                writer.writerow(row)
        logger.info("Wrote %s (%d finalists)", path, len(finalists))

    def _write_posteriors_csv(self, pack: EvaluationPack, out_dir: str) -> None:
        if not pack.posteriors:
            return
        path = os.path.join(out_dir, "posteriors.csv")
        fieldnames = list(pack.posteriors[0].keys()) if pack.posteriors else []
        if not fieldnames:
            return
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(pack.posteriors)
        logger.info("Wrote %s", path)

    def _record_in_db(self, campaign_id: str, out_dir: str, pack: EvaluationPack) -> None:
        """Record evaluation pack location in bt_evaluation_packs if table exists."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_evaluation_packs'"
            )
            if cur.fetchone():
                cur.execute(
                    """INSERT OR REPLACE INTO bt_evaluation_packs
                       (campaign_id, schema_version, artifact_dir, champion_id,
                        champion_title, champion_score, total_candidates, total_finalists,
                        embedding_provider, policy_used, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now'))""",
                    (
                        campaign_id,
                        pack.schema_version,
                        out_dir,
                        pack.champion_id,
                        pack.champion_title,
                        next(
                            (c.final_score for c in pack.all_candidates if c.candidate_id == pack.champion_id),
                            None,
                        ),
                        pack.total_candidates_generated,
                        pack.total_finalists,
                        pack.embedding_provider,
                        pack.policy_used,
                    ),
                )
                conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Could not record evaluation pack in DB: %s", e)


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def _render_markdown(pack: EvaluationPack) -> str:
    d = pack.to_dict()
    lines = []
    c = d["campaign"]
    cfg = d["config"]
    mdl = d["models"]
    stats = d["statistics"]
    champ = d.get("champion", {})
    champ_scores = champ.get("scores", {})
    finalists = d.get("finalists", [])
    tb = d.get("tiebreak_notes", {})

    lines.append(f"# Evaluation Pack: Campaign {c['campaign_id']}")
    lines.append(f"")
    lines.append(f"**Schema Version**: {d['schema_version']}")
    lines.append(f"**Generated**: Analysis-ready export for external inspection")
    lines.append(f"")

    lines.append(f"## Campaign Overview")
    lines.append(f"")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Campaign ID | `{c['campaign_id']}` |")
    lines.append(f"| Profile | {c['profile_name']} ({c['profile_type']}) |")
    lines.append(f"| Status | **{c['status']}** |")
    lines.append(f"| Started | {c['started_at']} |")
    lines.append(f"| Elapsed | {c['elapsed_seconds']:.0f}s ({c['elapsed_seconds']/60:.1f} min) |")
    lines.append(f"| Domain | {cfg['domain']} |")
    lines.append(f"| Program | {cfg['program_name']} |")
    lines.append(f"| Mode | {cfg['mode']} |")
    lines.append(f"| Generation Model | {mdl['generation_model']} |")
    lines.append(f"| Embedding Provider | {mdl['embedding_provider']} |")
    lines.append(f"| Embedding Model | {mdl['embedding_model']} |")
    lines.append(f"| Policy | {mdl['policy_used']} |")
    lines.append(f"")

    lines.append(f"## Statistics")
    lines.append(f"")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Candidates Generated | {stats['total_candidates_generated']} |")
    lines.append(f"| Candidates Blocked | {stats['total_candidates_blocked']} |")
    lines.append(f"| Shortlisted | {stats['total_shortlisted']} |")
    lines.append(f"| Finalists | {stats['total_finalists']} |")
    lines.append(f"| Total Runs | {stats['total_runs']} |")
    lines.append(f"")

    lines.append(f"## Preflight Health")
    lines.append(f"")
    pf = d["preflight"]
    lines.append(f"- Readiness Score: **{pf['readiness_score']:.2f}**")
    lines.append(f"- Pass: {pf['pass_count']} | Warn: {pf['warn_count']} | Fail: {pf['fail_count']}")
    lines.append(f"")

    if champ:
        lines.append(f"## Champion Candidate")
        lines.append(f"")
        lines.append(f"**ID**: `{champ.get('candidate_id', '')}`")
        lines.append(f"**Title**: {champ.get('title', '')}")
        lines.append(f"**Status**: {champ.get('status', '')}")
        lines.append(f"**Final Score**: **{champ_scores.get('final', 'N/A')}**")
        lines.append(f"")
        lines.append(f"### Score Breakdown")
        lines.append(f"")
        lines.append(f"| Dimension | Score |")
        lines.append(f"|-----------|-------|")
        for dim, val in champ_scores.items():
            if val is not None:
                lines.append(f"| {dim.replace('_', ' ').title()} | {val:.3f} |")
        lines.append(f"")
        lines.append(f"### Hypothesis")
        lines.append(f"")
        lines.append(f"**Statement**: {champ.get('statement', '')}")
        lines.append(f"")
        lines.append(f"**Mechanism**: {champ.get('mechanism', '')}")
        lines.append(f"")
        lines.append(f"**Expected Outcome**: {champ.get('expected_outcome', '')}")
        lines.append(f"")
        lines.append(f"**Novelty Notes**: {champ.get('novelty_notes', '')}")
        lines.append(f"")
        lines.append(f"**Testability Window**: {champ.get('testability_window_hours', 'N/A')} hours")
        lines.append(f"")
        if champ.get("assumptions"):
            lines.append(f"**Assumptions**:")
            for a in champ["assumptions"]:
                lines.append(f"- {a}")
            lines.append(f"")
        if champ.get("risk_flags"):
            lines.append(f"**Risk Flags**:")
            for r in champ["risk_flags"]:
                lines.append(f"- {r}")
            lines.append(f"")
        falsif = champ.get("falsification", {})
        if falsif:
            lines.append(f"**Falsification**: risk={falsif.get('risk', 'N/A')}, "
                         f"passed={falsif.get('passed', 'N/A')}, "
                         f"fragility={falsif.get('assumption_fragility_score', 'N/A')}")
            if falsif.get("reasoning"):
                lines.append(f"  — {falsif['reasoning']}")
            lines.append(f"")
        lines.append(f"**Why Champion**: {d.get('champion_rationale', 'N/A')}")
        lines.append(f"")

    if finalists:
        lines.append(f"## All Finalists")
        lines.append(f"")
        lines.append(f"| Rank | Score | Title | Falsif Risk | Why |")
        lines.append(f"|------|-------|-------|-------------|-----|")
        for entry in tb.get("ranked_finalists", []):
            fid = entry["candidate_id"]
            fcand = next((f for f in finalists if f["candidate_id"] == fid), {})
            falsif_risk = fcand.get("falsification", {}).get("risk", "N/A")
            mark = " **[CHAMPION]**" if entry["is_champion"] else ""
            lines.append(
                f"| {entry['rank']} | {entry['final_score']:.3f} | "
                f"{entry['title']}{mark} | {falsif_risk} | "
                f"{entry['why_ranked_here'][:80]} |"
            )
        lines.append(f"")

        lines.append(f"## Finalist Details")
        lines.append(f"")
        for i, fc in enumerate(finalists, 1):
            s = fc.get("scores", {})
            fal = fc.get("falsification", {})
            lines.append(f"### {i}. {fc.get('title', '')}")
            lines.append(f"**ID**: `{fc.get('candidate_id', '')}` | "
                         f"**Score**: {s.get('final', 'N/A')} | "
                         f"**Run**: `{fc.get('run_id', '')}`")
            lines.append(f"")
            lines.append(f"| Dimension | Score |")
            lines.append(f"|-----------|-------|")
            for dim, val in s.items():
                if val is not None:
                    lines.append(f"| {dim.replace('_',' ').title()} | {val:.3f} |")
            lines.append(f"")
            lines.append(f"**Statement**: {fc.get('statement', '')[:400]}")
            lines.append(f"")
            lines.append(f"**Falsification**: risk={fal.get('risk','N/A')}, "
                         f"passed={fal.get('passed','N/A')}, "
                         f"fragility={fal.get('assumption_fragility_score','N/A')}")
            lines.append(f"")

    if d.get("stage_events"):
        lines.append(f"## Stage Events")
        lines.append(f"")
        lines.append(f"| Stage | Status | Elapsed (s) | Retries |")
        lines.append(f"|-------|--------|-------------|---------|")
        for ev in d["stage_events"]:
            lines.append(
                f"| {ev.get('stage_name','')} | {ev.get('status','')} | "
                f"{ev.get('elapsed_seconds', 0.0):.1f} | {ev.get('retries', 0)} |"
            )
        lines.append(f"")

    if d.get("posteriors"):
        lines.append(f"## Bayesian Posteriors (Policy: {mdl['policy_used']})")
        lines.append(f"")
        lines.append(f"| Metric | n | Alpha | Beta | Last Updated |")
        lines.append(f"|--------|---|-------|------|--------------|")
        for p in d["posteriors"]:
            lines.append(
                f"| {p.get('metric_name','')} | {p.get('n',0)} | "
                f"{p.get('alpha',0):.3f} | {p.get('beta',0):.3f} | "
                f"{p.get('last_updated','')} |"
            )
        lines.append(f"")

    lines.append(f"---")
    lines.append(f"*Generated by Breakthrough Engine Phase 7B EvaluationPackExporter — "
                 f"schema {ANALYSIS_SCHEMA_VERSION}*")

    return "\n".join(lines)
