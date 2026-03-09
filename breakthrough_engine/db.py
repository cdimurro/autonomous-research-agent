"""Database initialization, migrations, and repository layer for the Breakthrough Engine.

All tables are prefixed with bt_ to avoid collision with existing scires.db tables.
Migrations are idempotent and versioned.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from .models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    DraftStatus,
    EvidenceItem,
    EvidencePack,
    HarnessDecision,
    NoveltyResult,
    PublicationDraft,
    PublicationRecord,
    ReviewAction,
    ReviewEvent,
    RunMetrics,
    RunRecord,
    RunStatus,
    SimulationResult,
    SimulationSpec,
)

def _utcnow() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

MIGRATIONS = {
    1: """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS bt_schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Run records
CREATE TABLE IF NOT EXISTS bt_runs (
    id TEXT PRIMARY KEY,
    program_name TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'demo_local',
    status TEXT NOT NULL DEFAULT 'started',
    candidates_generated INTEGER DEFAULT 0,
    candidates_rejected INTEGER DEFAULT 0,
    publication_id TEXT,
    error_message TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_runs_status ON bt_runs(status);

-- Candidates
CREATE TABLE IF NOT EXISTS bt_candidates (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES bt_runs(id),
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    statement TEXT NOT NULL,
    mechanism TEXT NOT NULL,
    expected_outcome TEXT NOT NULL,
    testability_window_hours REAL DEFAULT 24.0,
    novelty_notes TEXT DEFAULT '',
    assumptions TEXT DEFAULT '[]',
    risk_flags TEXT DEFAULT '[]',
    evidence_refs TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'generated',
    rejection_reason TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bt_cand_run ON bt_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_cand_status ON bt_candidates(status);

-- Evidence items
CREATE TABLE IF NOT EXISTS bt_evidence_items (
    id TEXT PRIMARY KEY,
    pack_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    quote TEXT NOT NULL,
    citation TEXT NOT NULL,
    relevance_score REAL DEFAULT 0.5
);
CREATE INDEX IF NOT EXISTS idx_bt_evi_pack ON bt_evidence_items(pack_id);

-- Evidence packs
CREATE TABLE IF NOT EXISTS bt_evidence_packs (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    source_diversity_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bt_ep_cand ON bt_evidence_packs(candidate_id);

-- Simulation specs
CREATE TABLE IF NOT EXISTS bt_simulation_specs (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    simulator TEXT NOT NULL DEFAULT 'mock',
    objective TEXT DEFAULT '',
    parameters TEXT DEFAULT '{}',
    constraints TEXT DEFAULT '{}',
    estimated_runtime_minutes REAL DEFAULT 5.0
);
CREATE INDEX IF NOT EXISTS idx_bt_ss_cand ON bt_simulation_specs(candidate_id);

-- Simulation results
CREATE TABLE IF NOT EXISTS bt_simulation_results (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    spec_id TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    key_metrics TEXT DEFAULT '{}',
    pass_fail_summary TEXT DEFAULT '',
    raw_artifact_path TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_sr_cand ON bt_simulation_results(candidate_id);

-- Harness decisions
CREATE TABLE IF NOT EXISTS bt_harness_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    harness_name TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    failed_rules TEXT DEFAULT '[]',
    warnings TEXT DEFAULT '[]',
    suggested_fixes TEXT DEFAULT '[]',
    score_contribution REAL DEFAULT 0.0,
    explanation TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_hd_cand ON bt_harness_decisions(candidate_id);

-- Scores
CREATE TABLE IF NOT EXISTS bt_scores (
    candidate_id TEXT PRIMARY KEY,
    novelty_score REAL DEFAULT 0.0,
    plausibility_score REAL DEFAULT 0.0,
    impact_score REAL DEFAULT 0.0,
    validation_cost_score REAL DEFAULT 0.0,
    evidence_strength_score REAL DEFAULT 0.0,
    simulation_readiness_score REAL DEFAULT 0.0,
    final_score REAL DEFAULT 0.0
);

-- Publications
CREATE TABLE IF NOT EXISTS bt_publications (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES bt_runs(id),
    publication_date TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_title TEXT NOT NULL,
    abstract TEXT DEFAULT '',
    hypothesis TEXT NOT NULL,
    score_breakdown TEXT DEFAULT '{}',
    evidence_summary TEXT DEFAULT '',
    simulation_summary TEXT DEFAULT '',
    assumptions TEXT DEFAULT '[]',
    uncertainties TEXT DEFAULT '[]',
    replication_priority TEXT DEFAULT 'medium',
    status_label TEXT NOT NULL DEFAULT 'validated_breakthrough_candidate'
);
CREATE INDEX IF NOT EXISTS idx_bt_pub_run ON bt_publications(run_id);

-- Rejections (denormalized for easy querying)
CREATE TABLE IF NOT EXISTS bt_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_title TEXT NOT NULL,
    status TEXT NOT NULL,
    rejection_reason TEXT NOT NULL,
    harness_name TEXT DEFAULT '',
    failed_rules TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_rej_run ON bt_rejections(run_id);
""",
    2: """
-- Phase 3: Novelty checks
CREATE TABLE IF NOT EXISTS bt_novelty_checks (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    novelty_score REAL DEFAULT 0.0,
    duplicate_risk_score REAL DEFAULT 0.0,
    prior_art_hits TEXT DEFAULT '[]',
    overlap_reasons TEXT DEFAULT '[]',
    decision TEXT NOT NULL DEFAULT 'pass',
    warnings TEXT DEFAULT '[]',
    explanation TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_nov_cand ON bt_novelty_checks(candidate_id);

-- Phase 3: Publication drafts
CREATE TABLE IF NOT EXISTS bt_publication_drafts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES bt_runs(id),
    candidate_id TEXT NOT NULL,
    candidate_title TEXT NOT NULL,
    abstract TEXT DEFAULT '',
    hypothesis TEXT NOT NULL,
    score_breakdown TEXT DEFAULT '{}',
    evidence_summary TEXT DEFAULT '',
    simulation_summary TEXT DEFAULT '',
    novelty_summary TEXT DEFAULT '',
    assumptions TEXT DEFAULT '[]',
    uncertainties TEXT DEFAULT '[]',
    replication_priority TEXT DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_pd_run ON bt_publication_drafts(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_pd_status ON bt_publication_drafts(status);

-- Phase 3: Review events
CREATE TABLE IF NOT EXISTS bt_review_events (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL REFERENCES bt_publication_drafts(id),
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reviewer TEXT DEFAULT 'operator',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_re_draft ON bt_review_events(draft_id);

-- Phase 3: Run metrics
CREATE TABLE IF NOT EXISTS bt_run_metrics (
    run_id TEXT PRIMARY KEY,
    stage_durations TEXT DEFAULT '{}',
    candidates_by_status TEXT DEFAULT '{}',
    evidence_count INTEGER DEFAULT 0,
    novelty_fail_count INTEGER DEFAULT 0,
    novelty_warn_count INTEGER DEFAULT 0,
    simulation_pass_count INTEGER DEFAULT 0,
    simulation_fail_count INTEGER DEFAULT 0,
    draft_created INTEGER DEFAULT 0,
    publication_created INTEGER DEFAULT 0,
    total_duration_seconds REAL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Phase 3: Retrieval cache
CREATE TABLE IF NOT EXISTS bt_retrieval_cache (
    cache_key TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    query TEXT NOT NULL,
    response_json TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bt_rc_source ON bt_retrieval_cache(source_name);
CREATE INDEX IF NOT EXISTS idx_bt_rc_expires ON bt_retrieval_cache(expires_at);
""",
    3: """
-- Phase 4B: Domain fit assessments
CREATE TABLE IF NOT EXISTS bt_domain_fit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    domain_fit_score REAL DEFAULT 0.0,
    title_relevance REAL DEFAULT 0.0,
    statement_relevance REAL DEFAULT 0.0,
    mechanism_relevance REAL DEFAULT 0.0,
    evidence_relevance REAL DEFAULT 0.0,
    relevance_reasons TEXT DEFAULT '[]',
    mismatch_flags TEXT DEFAULT '[]',
    matched_keywords TEXT DEFAULT '[]',
    passed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_df_cand ON bt_domain_fit(candidate_id);

-- Phase 4B: Embedding novelty details
CREATE TABLE IF NOT EXISTS bt_embedding_novelty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    embedding_similarity_max REAL DEFAULT 0.0,
    nearest_neighbors TEXT DEFAULT '[]',
    novelty_basis TEXT DEFAULT 'lexical_only',
    blocked_by_prior_art INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_en_cand ON bt_embedding_novelty(candidate_id);

-- Phase 4B: Evidence ranking details
CREATE TABLE IF NOT EXISTS bt_evidence_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    composite_score REAL DEFAULT 0.0,
    rank_explanation TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_er_cand ON bt_evidence_rankings(candidate_id);

-- Phase 4B: Publication gate diagnostics
CREATE TABLE IF NOT EXISTS bt_gate_diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    gate_name TEXT NOT NULL,
    passed INTEGER NOT NULL,
    score REAL DEFAULT 0.0,
    reasons TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_gd_run ON bt_gate_diagnostics(run_id);
""",
    4: """
-- Phase 4C: Embedding monitoring per-run
CREATE TABLE IF NOT EXISTS bt_embedding_monitor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT 'mock',
    embedding_dim INTEGER NOT NULL DEFAULT 64,
    similarity_threshold REAL NOT NULL DEFAULT 0.88,
    warn_threshold REAL NOT NULL DEFAULT 0.78,
    candidates_evaluated INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    warned_count INTEGER DEFAULT 0,
    max_similarity REAL DEFAULT 0.0,
    mean_similarity REAL DEFAULT 0.0,
    top_k_similarities TEXT DEFAULT '[]',
    nearest_neighbor_summary TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_em_run ON bt_embedding_monitor(run_id);

-- Phase 4C: Calibration diagnostics per-run
CREATE TABLE IF NOT EXISTS bt_calibration_diagnostics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    lexical_block_count INTEGER DEFAULT 0,
    embedding_block_count INTEGER DEFAULT 0,
    domain_fit_fail_count INTEGER DEFAULT 0,
    domain_fit_mean_score REAL DEFAULT 0.0,
    publication_pass_count INTEGER DEFAULT 0,
    publication_fail_count INTEGER DEFAULT 0,
    publication_fail_reasons TEXT DEFAULT '[]',
    draft_count INTEGER DEFAULT 0,
    candidate_count INTEGER DEFAULT 0,
    active_thresholds TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_cd_run ON bt_calibration_diagnostics(run_id);
""",
    5: """
-- Phase 4D: Diversity context used per run
CREATE TABLE IF NOT EXISTS bt_diversity_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    sub_domain TEXT DEFAULT '',
    excluded_topics TEXT DEFAULT '[]',
    excluded_neighbor_titles TEXT DEFAULT '[]',
    rotation_policy TEXT DEFAULT 'auto',
    focus_areas TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_dc_run ON bt_diversity_context(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_dc_domain ON bt_diversity_context(domain);

-- Phase 4D: Domain/sub-domain rotation state
CREATE TABLE IF NOT EXISTS bt_rotation_state (
    domain TEXT PRIMARY KEY,
    last_sub_domain TEXT DEFAULT '',
    sub_domain_index INTEGER DEFAULT 0,
    total_runs INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Phase 4D: Corpus archive marker
CREATE TABLE IF NOT EXISTS bt_corpus_archive (
    candidate_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    archived_reason TEXT DEFAULT 'recency',
    cluster_id TEXT DEFAULT '',
    archived_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_ca_domain ON bt_corpus_archive(domain);
""",
    7: """
-- Phase 6: Policy registry
CREATE TABLE IF NOT EXISTS bt_policies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0',
    config_json TEXT NOT NULL DEFAULT '{}',
    is_champion INTEGER NOT NULL DEFAULT 0,
    is_probation INTEGER NOT NULL DEFAULT 0,
    previous_champion_id TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_pol_champion ON bt_policies(is_champion);

-- Phase 6: Policy trials
CREATE TABLE IF NOT EXISTS bt_policy_trials (
    id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    trial_type TEXT NOT NULL DEFAULT 'benchmark',
    benchmark_metrics_json TEXT DEFAULT '{}',
    posterior_summary_json TEXT DEFAULT '{}',
    outcome TEXT DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_pt_policy ON bt_policy_trials(policy_id);

-- Phase 6: Bayesian posteriors (one row per policy+domain+metric combo, updated in-place)
CREATE TABLE IF NOT EXISTS bt_bayesian_posteriors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    observation_unit TEXT NOT NULL DEFAULT 'candidate',
    distribution_type TEXT NOT NULL DEFAULT 'beta_binomial',
    alpha REAL NOT NULL DEFAULT 1.0,
    beta REAL NOT NULL DEFAULT 1.0,
    mu REAL NOT NULL DEFAULT 0.0,
    M2 REAL NOT NULL DEFAULT 0.0,
    n INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    update_history_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE(policy_id, domain, metric_name)
);
CREATE INDEX IF NOT EXISTS idx_bt_bp_policy ON bt_bayesian_posteriors(policy_id);
CREATE INDEX IF NOT EXISTS idx_bt_bp_domain ON bt_bayesian_posteriors(domain);

-- Phase 6: Reward logs (atomic signal events)
CREATE TABLE IF NOT EXISTS bt_reward_logs (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    candidate_id TEXT DEFAULT '',
    policy_id TEXT DEFAULT '',
    observation_unit TEXT NOT NULL DEFAULT 'candidate',
    signal_name TEXT NOT NULL,
    signal_value REAL NOT NULL DEFAULT 0.0,
    signal_type TEXT NOT NULL DEFAULT 'binary',
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_rl_run ON bt_reward_logs(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_rl_policy ON bt_reward_logs(policy_id);
CREATE INDEX IF NOT EXISTS idx_bt_rl_signal ON bt_reward_logs(signal_name);

-- Phase 6: Trajectories (episode-level RL-ready summaries, one per run)
CREATE TABLE IF NOT EXISTS bt_trajectories (
    id TEXT PRIMARY KEY,
    trajectory_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    policy_id TEXT DEFAULT '',
    reward_recipe_version TEXT NOT NULL DEFAULT 'v1',
    state_json TEXT NOT NULL DEFAULT '{}',
    action_json TEXT NOT NULL DEFAULT '{}',
    reward REAL NOT NULL DEFAULT 0.0,
    reward_components_json TEXT NOT NULL DEFAULT '{}',
    outcome TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_traj_run ON bt_trajectories(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_traj_policy ON bt_trajectories(policy_id);

-- Phase 6: Baseline comparisons (comparison artifacts, not raw data)
CREATE TABLE IF NOT EXISTS bt_baseline_comparisons (
    id TEXT PRIMARY KEY,
    baseline_tag TEXT NOT NULL,
    baseline_commit TEXT DEFAULT '',
    current_branch TEXT DEFAULT '',
    current_commit TEXT DEFAULT '',
    comparison_report_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_bc_tag ON bt_baseline_comparisons(baseline_tag);

-- Phase 6: Falsification summaries (per candidate)
CREATE TABLE IF NOT EXISTS bt_falsification_summaries (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    contradictions_json TEXT NOT NULL DEFAULT '[]',
    missing_evidence_json TEXT NOT NULL DEFAULT '[]',
    assumption_fragility_score REAL NOT NULL DEFAULT 0.5,
    bridge_weakness_json TEXT NOT NULL DEFAULT '[]',
    falsification_risk TEXT NOT NULL DEFAULT 'medium',
    passed INTEGER NOT NULL DEFAULT 1,
    reasoning TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_fs_cand ON bt_falsification_summaries(candidate_id);
CREATE INDEX IF NOT EXISTS idx_bt_fs_run ON bt_falsification_summaries(run_id);

-- Phase 6: Daily search campaigns
CREATE TABLE IF NOT EXISTS bt_daily_campaigns (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'benchmark',
    policy_id TEXT DEFAULT '',
    champion_candidate_id TEXT DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_bt_dc_mode ON bt_daily_campaigns(mode);

-- Phase 6: Ladder stage events (one row per stage per campaign)
CREATE TABLE IF NOT EXISTS bt_ladder_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    trials_attempted INTEGER NOT NULL DEFAULT 0,
    candidates_advanced INTEGER NOT NULL DEFAULT 0,
    candidates_abandoned INTEGER NOT NULL DEFAULT 0,
    best_score REAL NOT NULL DEFAULT 0.0,
    best_candidate_id TEXT DEFAULT '',
    stop_reason TEXT NOT NULL DEFAULT 'completed',
    elapsed_seconds REAL NOT NULL DEFAULT 0.0,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_ls_campaign ON bt_ladder_stages(campaign_id);
""",
    6: """
-- Phase 5: Synthesis context per run
CREATE TABLE IF NOT EXISTS bt_synthesis_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    primary_domain TEXT NOT NULL,
    secondary_domain TEXT NOT NULL,
    primary_sub_domain TEXT DEFAULT '',
    secondary_sub_domain TEXT DEFAULT '',
    bridge_mechanism TEXT DEFAULT '',
    pairing_policy TEXT DEFAULT 'rotating_pair',
    excluded_cross_themes TEXT DEFAULT '[]',
    focus_angles TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_sc_run ON bt_synthesis_context(run_id);

-- Phase 5: Synthesis fit assessment per candidate
CREATE TABLE IF NOT EXISTS bt_synthesis_fit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    cross_domain_fit_score REAL DEFAULT 0.0,
    bridge_mechanism_score REAL DEFAULT 0.0,
    evidence_balance_score REAL DEFAULT 0.0,
    superficial_mashup_flag INTEGER DEFAULT 0,
    synthesis_reasons TEXT DEFAULT '[]',
    evidence_roles TEXT DEFAULT '{}',
    passed INTEGER DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_sf_cand ON bt_synthesis_fit(candidate_id);
""",
}


def _current_version(db: sqlite3.Connection) -> int:
    try:
        row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
        return row[0] if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        return 0


def init_db(db_path: Optional[str] = None, in_memory: bool = False) -> sqlite3.Connection:
    """Initialize or upgrade the breakthrough engine tables. Idempotent."""
    if in_memory:
        db = sqlite3.connect(":memory:")
    else:
        path = db_path or os.path.join(
            os.environ.get("SCIRES_RUNTIME_ROOT", "runtime"), "db", "scires.db"
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        db = sqlite3.connect(path)

    db.execute("PRAGMA journal_mode = WAL")
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    db.row_factory = sqlite3.Row

    current = _current_version(db)
    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            db.executescript(MIGRATIONS[version])
            db.execute(
                "INSERT INTO bt_schema_version (version) VALUES (?)", (version,)
            )
            db.commit()

    return db


# ---------------------------------------------------------------------------
# Repository helpers
# ---------------------------------------------------------------------------

def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


class Repository:
    """Data access layer for breakthrough engine entities."""

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    # -- Runs --

    def save_run(self, run: RunRecord) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_runs
               (id, program_name, mode, status, candidates_generated,
                candidates_rejected, publication_id, error_message,
                started_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (run.id, run.program_name, run.mode.value, run.status.value,
             run.candidates_generated, run.candidates_rejected,
             run.publication_id, run.error_message,
             _iso(run.started_at), _iso(run.completed_at)),
        )
        self.db.commit()

    def get_run(self, run_id: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM bt_runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Candidates --

    def save_candidate(self, c: CandidateHypothesis) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_candidates
               (id, run_id, title, domain, statement, mechanism,
                expected_outcome, testability_window_hours, novelty_notes,
                assumptions, risk_flags, evidence_refs, status,
                rejection_reason, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.id, c.run_id, c.title, c.domain, c.statement, c.mechanism,
             c.expected_outcome, c.testability_window_hours, c.novelty_notes,
             json.dumps(c.assumptions), json.dumps(c.risk_flags),
             json.dumps(c.evidence_refs), c.status.value,
             c.rejection_reason, _iso(c.created_at)),
        )
        self.db.commit()

    def update_candidate_status(
        self, candidate_id: str, status: CandidateStatus, reason: str = ""
    ) -> None:
        self.db.execute(
            "UPDATE bt_candidates SET status=?, rejection_reason=? WHERE id=?",
            (status.value, reason, candidate_id),
        )
        self.db.commit()

    def get_candidate(self, candidate_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_candidates WHERE id=?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_candidates_for_run(self, run_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_candidates WHERE run_id=? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_prior_candidates(self, domain: str, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_candidates WHERE domain=? ORDER BY created_at DESC LIMIT ?",
            (domain, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Evidence --

    def save_evidence_pack(self, pack: EvidencePack) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_evidence_packs
               (id, candidate_id, source_diversity_count, created_at)
               VALUES (?,?,?,?)""",
            (pack.id, pack.candidate_id, pack.source_diversity_count,
             _iso(pack.created_at)),
        )
        for item in pack.items:
            self.db.execute(
                """INSERT OR REPLACE INTO bt_evidence_items
                   (id, pack_id, source_type, source_id, title, quote,
                    citation, relevance_score)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (item.id, pack.id, item.source_type, item.source_id,
                 item.title, item.quote, item.citation, item.relevance_score),
            )
        self.db.commit()

    # -- Simulation --

    def save_simulation_spec(self, spec: SimulationSpec) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_simulation_specs
               (id, candidate_id, simulator, objective, parameters,
                constraints, estimated_runtime_minutes)
               VALUES (?,?,?,?,?,?,?)""",
            (spec.id, spec.candidate_id, spec.simulator, spec.objective,
             json.dumps(spec.parameters), json.dumps(spec.constraints),
             spec.estimated_runtime_minutes),
        )
        self.db.commit()

    def save_simulation_result(self, result: SimulationResult) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_simulation_results
               (id, candidate_id, spec_id, status, key_metrics,
                pass_fail_summary, raw_artifact_path, notes, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (result.id, result.candidate_id, result.spec_id,
             result.status.value, json.dumps(result.key_metrics),
             result.pass_fail_summary, result.raw_artifact_path,
             result.notes, _iso(result.completed_at)),
        )
        self.db.commit()

    # -- Harness decisions --

    def save_harness_decision(self, d: HarnessDecision) -> None:
        self.db.execute(
            """INSERT INTO bt_harness_decisions
               (harness_name, candidate_id, passed, failed_rules,
                warnings, suggested_fixes, score_contribution, explanation)
               VALUES (?,?,?,?,?,?,?,?)""",
            (d.harness_name, d.candidate_id, int(d.passed),
             json.dumps(d.failed_rules), json.dumps(d.warnings),
             json.dumps(d.suggested_fixes), d.score_contribution,
             d.explanation),
        )
        self.db.commit()

    def get_harness_decisions(self, candidate_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_harness_decisions WHERE candidate_id=? ORDER BY created_at",
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Scores --

    def save_score(self, score: CandidateScore) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_scores
               (candidate_id, novelty_score, plausibility_score, impact_score,
                validation_cost_score, evidence_strength_score,
                simulation_readiness_score, final_score)
               VALUES (?,?,?,?,?,?,?,?)""",
            (score.candidate_id, score.novelty_score, score.plausibility_score,
             score.impact_score, score.validation_cost_score,
             score.evidence_strength_score, score.simulation_readiness_score,
             score.final_score),
        )
        self.db.commit()

    def get_score(self, candidate_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_scores WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- Publications --

    def save_publication(self, pub: PublicationRecord) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_publications
               (id, run_id, publication_date, candidate_id, candidate_title,
                abstract, hypothesis, score_breakdown, evidence_summary,
                simulation_summary, assumptions, uncertainties,
                replication_priority, status_label)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pub.id, pub.run_id, _iso(pub.publication_date),
             pub.candidate_id, pub.candidate_title, pub.abstract,
             pub.hypothesis, json.dumps(pub.score_breakdown),
             pub.evidence_summary, pub.simulation_summary,
             json.dumps(pub.assumptions), json.dumps(pub.uncertainties),
             pub.replication_priority, pub.status_label),
        )
        self.db.commit()

    def get_publication(self, pub_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_publications WHERE id=?", (pub_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_publications(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_publications ORDER BY publication_date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Rejections --

    def save_rejection(
        self,
        run_id: str,
        candidate_id: str,
        candidate_title: str,
        status: CandidateStatus,
        reason: str,
        harness_name: str = "",
        failed_rules: Optional[list[str]] = None,
    ) -> None:
        self.db.execute(
            """INSERT INTO bt_rejections
               (run_id, candidate_id, candidate_title, status,
                rejection_reason, harness_name, failed_rules)
               VALUES (?,?,?,?,?,?,?)""",
            (run_id, candidate_id, candidate_title, status.value,
             reason, harness_name, json.dumps(failed_rules or [])),
        )
        self.db.commit()

    def list_rejections(self, run_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_rejections WHERE run_id=? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Novelty checks --

    def save_novelty_check(self, n: NoveltyResult) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_novelty_checks
               (id, candidate_id, novelty_score, duplicate_risk_score,
                prior_art_hits, overlap_reasons, decision, warnings,
                explanation, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (n.id, n.candidate_id, n.novelty_score, n.duplicate_risk_score,
             json.dumps([h.model_dump() for h in n.prior_art_hits]),
             json.dumps(n.overlap_reasons), n.decision.value,
             json.dumps(n.warnings), n.explanation, _iso(n.created_at)),
        )
        self.db.commit()

    def get_novelty_check(self, candidate_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_novelty_checks WHERE candidate_id=?",
            (candidate_id,),
        ).fetchone()
        return dict(row) if row else None

    # -- Publication drafts --

    def save_draft(self, draft: PublicationDraft) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_publication_drafts
               (id, run_id, candidate_id, candidate_title, abstract,
                hypothesis, score_breakdown, evidence_summary,
                simulation_summary, novelty_summary, assumptions,
                uncertainties, replication_priority, status,
                created_at, reviewed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (draft.id, draft.run_id, draft.candidate_id,
             draft.candidate_title, draft.abstract, draft.hypothesis,
             json.dumps(draft.score_breakdown), draft.evidence_summary,
             draft.simulation_summary, draft.novelty_summary,
             json.dumps(draft.assumptions), json.dumps(draft.uncertainties),
             draft.replication_priority, draft.status.value,
             _iso(draft.created_at), _iso(draft.reviewed_at)),
        )
        self.db.commit()

    def get_draft(self, draft_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_publication_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_draft_by_run(self, run_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_publication_drafts WHERE run_id=?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_drafts(self, status: Optional[str] = None, limit: int = 20) -> list[dict]:
        if status:
            rows = self.db.execute(
                "SELECT * FROM bt_publication_drafts WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM bt_publication_drafts ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_draft_status(self, draft_id: str, status: DraftStatus) -> None:
        reviewed_at = _iso(datetime.now(timezone.utc).replace(tzinfo=None)) if status != DraftStatus.PENDING_REVIEW else None
        self.db.execute(
            "UPDATE bt_publication_drafts SET status=?, reviewed_at=? WHERE id=?",
            (status.value, reviewed_at, draft_id),
        )
        self.db.commit()

    # -- Review events --

    def save_review_event(self, event: ReviewEvent) -> None:
        self.db.execute(
            """INSERT INTO bt_review_events
               (id, draft_id, run_id, candidate_id, action, reviewer, notes, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (event.id, event.draft_id, event.run_id, event.candidate_id,
             event.action.value, event.reviewer, event.notes,
             _iso(event.created_at)),
        )
        self.db.commit()

    def list_review_events(self, draft_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_review_events WHERE draft_id=? ORDER BY created_at",
            (draft_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Run metrics --

    def save_run_metrics(self, m: RunMetrics) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_run_metrics
               (run_id, stage_durations, candidates_by_status, evidence_count,
                novelty_fail_count, novelty_warn_count,
                simulation_pass_count, simulation_fail_count,
                draft_created, publication_created,
                total_duration_seconds, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m.run_id, json.dumps(m.stage_durations),
             json.dumps(m.candidates_by_status), m.evidence_count,
             m.novelty_fail_count, m.novelty_warn_count,
             m.simulation_pass_count, m.simulation_fail_count,
             int(m.draft_created), int(m.publication_created),
             m.total_duration_seconds, _iso(m.created_at)),
        )
        self.db.commit()

    def get_run_metrics(self, run_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_run_metrics WHERE run_id=?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_recent_metrics(self, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_run_metrics ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Retrieval cache --

    def get_cached_retrieval(self, cache_key: str) -> Optional[str]:
        row = self.db.execute(
            "SELECT response_json FROM bt_retrieval_cache WHERE cache_key=? AND expires_at > strftime('%Y-%m-%dT%H:%M:%SZ','now')",
            (cache_key,),
        ).fetchone()
        return row[0] if row else None

    def save_cached_retrieval(
        self, cache_key: str, source_name: str, query: str,
        response_json: str, result_count: int, ttl_hours: int = 24,
    ) -> None:
        from datetime import timedelta
        expires = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=ttl_hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.db.execute(
            """INSERT OR REPLACE INTO bt_retrieval_cache
               (cache_key, source_name, query, response_json, result_count,
                created_at, expires_at)
               VALUES (?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%SZ','now'),?)""",
            (cache_key, source_name, query, response_json, result_count, expires),
        )
        self.db.commit()

    def clear_expired_cache(self) -> int:
        cursor = self.db.execute(
            "DELETE FROM bt_retrieval_cache WHERE expires_at <= strftime('%Y-%m-%dT%H:%M:%SZ','now')"
        )
        self.db.commit()
        return cursor.rowcount

    # -- Phase 4B: Domain fit --

    def save_domain_fit(self, fit: dict) -> None:
        self.db.execute(
            """INSERT INTO bt_domain_fit
               (candidate_id, domain, domain_fit_score, title_relevance,
                statement_relevance, mechanism_relevance, evidence_relevance,
                relevance_reasons, mismatch_flags, matched_keywords, passed)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (fit["candidate_id"], fit["domain"], fit["domain_fit_score"],
             fit["title_relevance"], fit["statement_relevance"],
             fit["mechanism_relevance"], fit["evidence_relevance"],
             json.dumps(fit.get("relevance_reasons", [])),
             json.dumps(fit.get("mismatch_flags", [])),
             json.dumps(fit.get("matched_keywords", [])),
             int(fit.get("passed", True))),
        )
        self.db.commit()

    def get_domain_fit(self, candidate_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_domain_fit WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- Phase 4B: Embedding novelty --

    def save_embedding_novelty(self, detail: dict) -> None:
        self.db.execute(
            """INSERT INTO bt_embedding_novelty
               (candidate_id, embedding_similarity_max, nearest_neighbors,
                novelty_basis, blocked_by_prior_art)
               VALUES (?,?,?,?,?)""",
            (detail["candidate_id"], detail.get("embedding_similarity_max", 0.0),
             json.dumps(detail.get("nearest_neighbors", [])),
             detail.get("novelty_basis", "lexical_only"),
             int(detail.get("blocked_by_prior_art", False))),
        )
        self.db.commit()

    def get_embedding_novelty(self, candidate_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_embedding_novelty WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- Phase 4B: Gate diagnostics --

    def save_gate_diagnostic(
        self, run_id: str, candidate_id: str, gate_name: str,
        passed: bool, score: float = 0.0, reasons: list[str] | None = None,
    ) -> None:
        self.db.execute(
            """INSERT INTO bt_gate_diagnostics
               (run_id, candidate_id, gate_name, passed, score, reasons)
               VALUES (?,?,?,?,?,?)""",
            (run_id, candidate_id, gate_name, int(passed), score,
             json.dumps(reasons or [])),
        )
        self.db.commit()

    def list_gate_diagnostics(self, run_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_gate_diagnostics WHERE run_id=? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Phase 4B: Evidence rankings --

    def save_evidence_ranking(
        self, candidate_id: str, evidence_id: str,
        composite_score: float, rank_explanation: str,
    ) -> None:
        self.db.execute(
            """INSERT INTO bt_evidence_rankings
               (candidate_id, evidence_id, composite_score, rank_explanation)
               VALUES (?,?,?,?)""",
            (candidate_id, evidence_id, composite_score, rank_explanation),
        )
        self.db.commit()

    def list_evidence_rankings(self, candidate_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_evidence_rankings WHERE candidate_id=? ORDER BY composite_score DESC",
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Phase 4C: Embedding monitoring --

    def save_embedding_monitor(self, data: dict) -> None:
        self.db.execute(
            """INSERT INTO bt_embedding_monitor
               (run_id, embedding_model, embedding_dim, similarity_threshold,
                warn_threshold, candidates_evaluated, blocked_count, warned_count,
                max_similarity, mean_similarity, top_k_similarities,
                nearest_neighbor_summary)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data["run_id"], data.get("embedding_model", "mock"),
             data.get("embedding_dim", 64),
             data.get("similarity_threshold", 0.88),
             data.get("warn_threshold", 0.78),
             data.get("candidates_evaluated", 0),
             data.get("blocked_count", 0),
             data.get("warned_count", 0),
             data.get("max_similarity", 0.0),
             data.get("mean_similarity", 0.0),
             json.dumps(data.get("top_k_similarities", [])),
             json.dumps(data.get("nearest_neighbor_summary", []))),
        )
        self.db.commit()

    def get_embedding_monitor(self, run_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_embedding_monitor WHERE run_id=?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_embedding_monitors(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_embedding_monitor ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Phase 4C: Calibration diagnostics --

    def save_calibration_diagnostic(self, data: dict) -> None:
        self.db.execute(
            """INSERT INTO bt_calibration_diagnostics
               (run_id, lexical_block_count, embedding_block_count,
                domain_fit_fail_count, domain_fit_mean_score,
                publication_pass_count, publication_fail_count,
                publication_fail_reasons, draft_count, candidate_count,
                active_thresholds)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (data["run_id"],
             data.get("lexical_block_count", 0),
             data.get("embedding_block_count", 0),
             data.get("domain_fit_fail_count", 0),
             data.get("domain_fit_mean_score", 0.0),
             data.get("publication_pass_count", 0),
             data.get("publication_fail_count", 0),
             json.dumps(data.get("publication_fail_reasons", [])),
             data.get("draft_count", 0),
             data.get("candidate_count", 0),
             json.dumps(data.get("active_thresholds", {}))),
        )
        self.db.commit()

    def get_calibration_diagnostic(self, run_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_calibration_diagnostics WHERE run_id=?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_calibration_diagnostics(self, limit: int = 20) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_calibration_diagnostics ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        return [dict(r) for r in rows]

    # -- Phase 4D: Diversity context --

    def save_diversity_context(self, data: dict) -> None:
        now = _utcnow()
        self.db.execute(
            """INSERT INTO bt_diversity_context
               (run_id, domain, sub_domain, excluded_topics,
                excluded_neighbor_titles, rotation_policy, focus_areas, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                data["run_id"],
                data["domain"],
                data.get("sub_domain", ""),
                json.dumps(data.get("excluded_topics", [])),
                json.dumps(data.get("excluded_neighbor_titles", [])),
                data.get("rotation_policy", "auto"),
                json.dumps(data.get("focus_areas", [])),
                now,
            ),
        )
        self.db.commit()

    def get_diversity_context(self, run_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_diversity_context WHERE run_id=? ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("excluded_topics", "excluded_neighbor_titles", "focus_areas"):
            if isinstance(d.get(key), str):
                d[key] = json.loads(d[key])
        return d

    # -- Phase 4D: Rotation state --

    def get_rotation_state(self, domain: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_rotation_state WHERE domain=?", (domain,)
        ).fetchone()
        return dict(row) if row else None

    def save_rotation_state(
        self, domain: str, sub_domain: str, index: int, total: int
    ) -> None:
        now = _utcnow()
        self.db.execute(
            """INSERT INTO bt_rotation_state
               (domain, last_sub_domain, sub_domain_index, total_runs, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(domain) DO UPDATE SET
                 last_sub_domain=excluded.last_sub_domain,
                 sub_domain_index=excluded.sub_domain_index,
                 total_runs=excluded.total_runs,
                 updated_at=excluded.updated_at""",
            (domain, sub_domain, index, total, now),
        )
        self.db.commit()

    # -- Phase 4D: Corpus archive --

    def archive_candidate(
        self, candidate_id: str, domain: str, reason: str = "recency", cluster_id: str = ""
    ) -> None:
        now = _utcnow()
        self.db.execute(
            """INSERT OR IGNORE INTO bt_corpus_archive
               (candidate_id, domain, archived_reason, cluster_id, archived_at)
               VALUES (?,?,?,?,?)""",
            (candidate_id, domain, reason, cluster_id, now),
        )
        self.db.commit()

    def list_archived_candidates(self, domain: str, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_corpus_archive WHERE domain=? ORDER BY archived_at DESC LIMIT ?",
            (domain, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def is_archived(self, candidate_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM bt_corpus_archive WHERE candidate_id=?", (candidate_id,)
        ).fetchone()
        return row is not None

    # -- Phase 5: Synthesis context --

    def save_synthesis_context(self, data: dict) -> None:
        now = _utcnow()
        self.db.execute(
            """INSERT INTO bt_synthesis_context
               (run_id, primary_domain, secondary_domain, primary_sub_domain,
                secondary_sub_domain, bridge_mechanism, pairing_policy,
                excluded_cross_themes, focus_angles, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                data["run_id"],
                data["primary_domain"],
                data["secondary_domain"],
                data.get("primary_sub_domain", ""),
                data.get("secondary_sub_domain", ""),
                data.get("bridge_mechanism", ""),
                data.get("pairing_policy", "rotating_pair"),
                json.dumps(data.get("excluded_cross_themes", [])),
                json.dumps(data.get("focus_angles", [])),
                now,
            ),
        )
        self.db.commit()

    def get_synthesis_context(self, run_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_synthesis_context WHERE run_id=? ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        for key in ("excluded_cross_themes", "focus_angles"):
            if isinstance(d.get(key), str):
                d[key] = json.loads(d[key])
        return d

    # -- Phase 5: Synthesis fit --

    def save_synthesis_fit(self, data: dict) -> None:
        self.db.execute(
            """INSERT INTO bt_synthesis_fit
               (candidate_id, cross_domain_fit_score, bridge_mechanism_score,
                evidence_balance_score, superficial_mashup_flag,
                synthesis_reasons, evidence_roles, passed)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                data["candidate_id"],
                data.get("cross_domain_fit_score", 0.0),
                data.get("bridge_mechanism_score", 0.0),
                data.get("evidence_balance_score", 0.0),
                int(data.get("superficial_mashup_flag", False)),
                json.dumps(data.get("synthesis_reasons", [])),
                json.dumps(data.get("evidence_roles", {})),
                int(data.get("passed", True)),
            ),
        )
        self.db.commit()

    def get_synthesis_fit(self, candidate_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_synthesis_fit WHERE candidate_id=?",
            (candidate_id,),
        ).fetchone()
        return dict(row) if row else None
