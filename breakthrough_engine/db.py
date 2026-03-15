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
from .domain_models import (
    CandidateSpec,
    EvaluationResult,
    ExperimentMemoryEntry,
    ExperimentRunResult,
    IdeaMemoryEntry,
    PromotionRecord,
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
    8: """
-- Phase 7A: Campaign receipts (one row per autonomous campaign)
CREATE TABLE IF NOT EXISTS bt_campaign_receipts (
    campaign_id TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL DEFAULT '',
    profile_type TEXT NOT NULL DEFAULT 'pilot',
    status TEXT NOT NULL DEFAULT 'preflight',
    config_json TEXT NOT NULL DEFAULT '{}',
    preflight_json TEXT NOT NULL DEFAULT '{}',
    stage_events_json TEXT NOT NULL DEFAULT '[]',
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at TEXT,
    elapsed_seconds REAL DEFAULT 0.0,
    champion_candidate_id TEXT DEFAULT '',
    champion_candidate_title TEXT DEFAULT '',
    draft_id TEXT DEFAULT '',
    failure_reason TEXT DEFAULT '',
    total_candidates_generated INTEGER DEFAULT 0,
    total_blocked INTEGER DEFAULT 0,
    total_shortlisted INTEGER DEFAULT 0,
    policy_trials_attempted INTEGER DEFAULT 0,
    retries_used INTEGER DEFAULT 0,
    artifact_paths_json TEXT NOT NULL DEFAULT '[]',
    health_summary_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_bt_cr_status ON bt_campaign_receipts(status);
CREATE INDEX IF NOT EXISTS idx_bt_cr_profile ON bt_campaign_receipts(profile_name);

-- Phase 7A: Preflight check results (one set per campaign)
CREATE TABLE IF NOT EXISTS bt_preflight_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PASS',
    detail TEXT DEFAULT '',
    remediation TEXT DEFAULT '',
    elapsed_ms REAL DEFAULT 0.0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_pr_campaign ON bt_preflight_results(campaign_id);

-- Phase 7A: Campaign heartbeats (watchdog telemetry)
CREATE TABLE IF NOT EXISTS bt_campaign_heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    stage_name TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_ch_campaign ON bt_campaign_heartbeats(campaign_id);
""",
    9: """
-- Phase 7B: Evaluation packs tracking table
CREATE TABLE IF NOT EXISTS bt_evaluation_packs (
    campaign_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT 'v001',
    artifact_dir TEXT NOT NULL DEFAULT '',
    champion_id TEXT DEFAULT '',
    champion_title TEXT DEFAULT '',
    champion_score REAL,
    total_candidates INTEGER DEFAULT 0,
    total_finalists INTEGER DEFAULT 0,
    embedding_provider TEXT NOT NULL DEFAULT 'MockEmbeddingProvider',
    policy_used TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Phase 7B: Add embedding_provider column to campaign receipts
ALTER TABLE bt_campaign_receipts ADD COLUMN embedding_provider TEXT NOT NULL DEFAULT 'MockEmbeddingProvider';
""",
    10: """
-- Phase 7D: Structured human review labels for champion and runner-up finalists.
-- Ground-truth signal for Bayesian policy optimization.
CREATE TABLE IF NOT EXISTS bt_review_labels (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_title TEXT NOT NULL DEFAULT '',
    candidate_role TEXT NOT NULL DEFAULT 'finalist',
    decision TEXT NOT NULL DEFAULT 'defer',
    novelty_confidence REAL DEFAULT 0.5,
    technical_plausibility REAL DEFAULT 0.5,
    commercialization_relevance REAL DEFAULT 0.5,
    key_flaw TEXT DEFAULT '',
    reviewer_note TEXT DEFAULT '',
    reviewer TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_rl_campaign ON bt_review_labels(campaign_id);
CREATE INDEX IF NOT EXISTS idx_bt_rl_candidate ON bt_review_labels(candidate_id);
CREATE INDEX IF NOT EXISTS idx_bt_rl_decision ON bt_review_labels(decision);
""",
    11: """
-- Phase 8: Reviewed baselines, review queue, daily automation runs, policy promotion log.
-- NOTE: ALTER TABLE bt_policies ADD COLUMN is_rolled_back is handled separately in init_db.

-- Frozen baseline references (Phase 5, Phase 7D, future).
CREATE TABLE IF NOT EXISTS bt_reviewed_baselines (
    baseline_id TEXT PRIMARY KEY,
    baseline_name TEXT NOT NULL,
    baseline_type TEXT NOT NULL DEFAULT 'reviewed_evaluation',
    frozen_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    branch TEXT NOT NULL DEFAULT '',
    commit_hash TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '',
    profile TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    baseline_json TEXT NOT NULL DEFAULT '{}',
    is_read_only INTEGER NOT NULL DEFAULT 1
);

-- Review queue: items awaiting human review after daily automation.
CREATE TABLE IF NOT EXISTS bt_review_queue (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL,
    daily_run_id TEXT NOT NULL DEFAULT '',
    profile_name TEXT NOT NULL DEFAULT '',
    policy_id TEXT NOT NULL DEFAULT '',
    champion_title TEXT NOT NULL DEFAULT '',
    champion_score REAL DEFAULT 0.0,
    champion_candidate_id TEXT NOT NULL DEFAULT '',
    falsification_summary TEXT NOT NULL DEFAULT '',
    rationale TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'completed_with_draft',
    review_status TEXT NOT NULL DEFAULT 'pending',
    inserted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    reviewed_at TEXT DEFAULT NULL,
    reviewer TEXT DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_bt_rq_campaign ON bt_review_queue(campaign_id);
CREATE INDEX IF NOT EXISTS idx_bt_rq_status ON bt_review_queue(review_status);
CREATE INDEX IF NOT EXISTS idx_bt_rq_inserted ON bt_review_queue(inserted_at);

-- Daily automation run records.
CREATE TABLE IF NOT EXISTS bt_daily_automation_runs (
    id TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL,
    campaign_id TEXT NOT NULL DEFAULT '',
    policy_id TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'unknown',
    dry_run INTEGER NOT NULL DEFAULT 0,
    error_message TEXT DEFAULT '',
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    completed_at TEXT DEFAULT NULL,
    run_date TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_dar_profile ON bt_daily_automation_runs(profile_name);
CREATE INDEX IF NOT EXISTS idx_bt_dar_date ON bt_daily_automation_runs(run_date);

-- Policy promotion audit log.
CREATE TABLE IF NOT EXISTS bt_policy_promotion_log (
    id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    policy_name TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    from_state TEXT NOT NULL DEFAULT '',
    to_state TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_ppl_policy ON bt_policy_promotion_log(policy_id);
CREATE INDEX IF NOT EXISTS idx_bt_ppl_event ON bt_policy_promotion_log(event_type);
""",
    12: """
-- Phase 10A: Knowledge Graph shadow foundation tables.

-- Paper segments staging layer.
CREATE TABLE IF NOT EXISTS bt_paper_segments (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    segment_index INTEGER NOT NULL DEFAULT 0,
    raw_text TEXT NOT NULL DEFAULT '',
    compressed_text TEXT DEFAULT '',
    relevance_score REAL DEFAULT 0.0,
    domain TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ingested',
    embedding_json TEXT DEFAULT NULL,
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    summarized_at TEXT DEFAULT NULL,
    error_message TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bt_ps_paper ON bt_paper_segments(paper_id);
CREATE INDEX IF NOT EXISTS idx_bt_ps_domain ON bt_paper_segments(domain);
CREATE INDEX IF NOT EXISTS idx_bt_ps_status ON bt_paper_segments(status);

-- KG entities extracted from paper segments.
CREATE TABLE IF NOT EXISTS bt_kg_entities (
    id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL,
    paper_id TEXT NOT NULL DEFAULT '',
    entity_type TEXT NOT NULL DEFAULT 'concept',
    name TEXT NOT NULL,
    canonical_name TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    domain TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'extracted',
    extracted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    error_message TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bt_kge_segment ON bt_kg_entities(segment_id);
CREATE INDEX IF NOT EXISTS idx_bt_kge_type ON bt_kg_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_bt_kge_name ON bt_kg_entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_bt_kge_domain ON bt_kg_entities(domain);

-- KG relations extracted from paper segments.
CREATE TABLE IF NOT EXISTS bt_kg_relations (
    id TEXT PRIMARY KEY,
    segment_id TEXT NOT NULL,
    paper_id TEXT NOT NULL DEFAULT '',
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'related_to',
    description TEXT DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    domain TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'extracted',
    extracted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    error_message TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_bt_kgr_segment ON bt_kg_relations(segment_id);
CREATE INDEX IF NOT EXISTS idx_bt_kgr_source ON bt_kg_relations(source_entity_id);
CREATE INDEX IF NOT EXISTS idx_bt_kgr_target ON bt_kg_relations(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_bt_kgr_type ON bt_kg_relations(relation_type);
CREATE INDEX IF NOT EXISTS idx_bt_kgr_domain ON bt_kg_relations(domain);

-- KG findings: write-back of published candidates for temporal knowledge.
CREATE TABLE IF NOT EXISTS bt_kg_findings (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    publication_id TEXT DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    statement TEXT NOT NULL DEFAULT '',
    mechanism TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    valid_from TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_until TEXT DEFAULT NULL,
    superseded_by TEXT DEFAULT NULL,
    source_evidence_ids TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_kgf_candidate ON bt_kg_findings(candidate_id);
CREATE INDEX IF NOT EXISTS idx_bt_kgf_domain ON bt_kg_findings(domain);
CREATE INDEX IF NOT EXISTS idx_bt_kgf_status ON bt_kg_findings(status);
CREATE INDEX IF NOT EXISTS idx_bt_kgf_valid ON bt_kg_findings(valid_from);
""",
    13: """
-- Domain optimization loop tables (PV foundation loop batch).

-- Domain-specific candidates.
CREATE TABLE IF NOT EXISTS bt_domain_candidates (
    id TEXT PRIMARY KEY,
    domain_name TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parameters TEXT NOT NULL DEFAULT '{}',
    rationale TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'generated',
    parent_id TEXT DEFAULT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    rejection_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_dc_domain ON bt_domain_candidates(domain_name);
CREATE INDEX IF NOT EXISTS idx_bt_dc_run ON bt_domain_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_dc_status ON bt_domain_candidates(status);

-- Experiment run results.
CREATE TABLE IF NOT EXISTS bt_experiment_results (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    template_id TEXT NOT NULL DEFAULT '',
    domain_name TEXT NOT NULL,
    metrics TEXT NOT NULL DEFAULT '{}',
    raw_data TEXT NOT NULL DEFAULT '{}',
    duration_seconds REAL DEFAULT 0.0,
    success INTEGER NOT NULL DEFAULT 1,
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_er_candidate ON bt_experiment_results(candidate_id);
CREATE INDEX IF NOT EXISTS idx_bt_er_domain ON bt_experiment_results(domain_name);

-- Evaluation results (scored).
CREATE TABLE IF NOT EXISTS bt_evaluation_results (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    domain_name TEXT NOT NULL,
    score_components TEXT NOT NULL DEFAULT '{}',
    final_score REAL DEFAULT 0.0,
    hard_fail INTEGER NOT NULL DEFAULT 0,
    hard_fail_reasons TEXT NOT NULL DEFAULT '[]',
    caveats TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_eval_candidate ON bt_evaluation_results(candidate_id);
CREATE INDEX IF NOT EXISTS idx_bt_eval_domain ON bt_evaluation_results(domain_name);

-- Promotion decisions.
CREATE TABLE IF NOT EXISTS bt_promotion_records (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    domain_name TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT 'rejected',
    evaluation_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    baseline_score REAL DEFAULT NULL,
    candidate_score REAL DEFAULT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_pr_candidate ON bt_promotion_records(candidate_id);
CREATE INDEX IF NOT EXISTS idx_bt_pr_domain ON bt_promotion_records(domain_name);

-- Idea memory.
CREATE TABLE IF NOT EXISTS bt_idea_memory (
    id TEXT PRIMARY KEY,
    domain_name TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    candidate_title TEXT NOT NULL DEFAULT '',
    candidate_family TEXT NOT NULL DEFAULT '',
    rationale TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    lesson TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_im_domain ON bt_idea_memory(domain_name);
CREATE INDEX IF NOT EXISTS idx_bt_im_family ON bt_idea_memory(candidate_family);

-- Experiment memory.
CREATE TABLE IF NOT EXISTS bt_experiment_memory (
    id TEXT PRIMARY KEY,
    domain_name TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    template_name TEXT NOT NULL DEFAULT '',
    informative_metrics TEXT NOT NULL DEFAULT '[]',
    weakness_exposed TEXT NOT NULL DEFAULT '',
    stability_notes TEXT NOT NULL DEFAULT '',
    runtime_seconds REAL DEFAULT 0.0,
    reproducibility_score REAL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_bt_em_domain ON bt_experiment_memory(domain_name);
CREATE INDEX IF NOT EXISTS idx_bt_em_candidate ON bt_experiment_memory(candidate_id);
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

    # Phase 8: add is_rolled_back column to bt_policies if not present (ALTER TABLE cannot
    # run inside executescript safely, so we apply it here with best-effort).
    try:
        db.execute("ALTER TABLE bt_policies ADD COLUMN is_rolled_back INTEGER NOT NULL DEFAULT 0")
        db.commit()
    except Exception:
        pass  # Column already exists — idempotent

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

    # -- Phase 7D: Review labels --

    def save_review_label(self, label: dict) -> None:
        """Insert or replace a structured human review label for a candidate."""
        from .models import new_id as _new_id
        label_id = label.get("id") or _new_id()
        self.db.execute(
            """INSERT OR REPLACE INTO bt_review_labels
               (id, campaign_id, candidate_id, candidate_title, candidate_role,
                decision, novelty_confidence, technical_plausibility,
                commercialization_relevance, key_flaw, reviewer_note, reviewer)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                label_id,
                label["campaign_id"],
                label["candidate_id"],
                label.get("candidate_title", ""),
                label.get("candidate_role", "finalist"),
                label.get("decision", "defer"),
                label.get("novelty_confidence", 0.5),
                label.get("technical_plausibility", 0.5),
                label.get("commercialization_relevance", 0.5),
                label.get("key_flaw", ""),
                label.get("reviewer_note", ""),
                label.get("reviewer", "operator"),
            ),
        )
        self.db.commit()

    def get_review_labels_for_campaign(self, campaign_id: str) -> list[dict]:
        """Return all review labels for a campaign, ordered by candidate_role."""
        rows = self.db.execute(
            """SELECT * FROM bt_review_labels
               WHERE campaign_id = ?
               ORDER BY CASE candidate_role
                 WHEN 'champion' THEN 0
                 WHEN 'runner_up' THEN 1
                 ELSE 2
               END, created_at""",
            (campaign_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_all_review_labels(self) -> list[dict]:
        """Return all review labels across all campaigns."""
        rows = self.db.execute(
            "SELECT * FROM bt_review_labels ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Phase 8: Review queue --

    def insert_review_queue_item(self, item: dict) -> str:
        """Insert a review queue item. Returns the item id."""
        from .models import new_id as _new_id
        item_id = item.get("id") or _new_id()
        self.db.execute(
            """INSERT OR REPLACE INTO bt_review_queue
               (id, campaign_id, daily_run_id, profile_name, policy_id,
                champion_title, champion_score, champion_candidate_id,
                falsification_summary, rationale, outcome, review_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                item_id,
                item.get("campaign_id", ""),
                item.get("daily_run_id", ""),
                item.get("profile_name", ""),
                item.get("policy_id", ""),
                item.get("champion_title", ""),
                item.get("champion_score", 0.0),
                item.get("champion_candidate_id", ""),
                item.get("falsification_summary", ""),
                item.get("rationale", ""),
                item.get("outcome", "completed_with_draft"),
                item.get("review_status", "pending"),
            ),
        )
        self.db.commit()
        return item_id

    def list_review_queue(self, review_status: str = "pending") -> list[dict]:
        """Return review queue items, optionally filtered by status."""
        if review_status == "all":
            rows = self.db.execute(
                "SELECT * FROM bt_review_queue ORDER BY inserted_at DESC"
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM bt_review_queue WHERE review_status=? ORDER BY inserted_at DESC",
                (review_status,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_review_queue_item_reviewed(
        self, item_id: str, reviewer: str = "operator"
    ) -> None:
        """Mark a review queue item as reviewed."""
        self.db.execute(
            """UPDATE bt_review_queue
               SET review_status='reviewed', reviewed_at=(strftime('%Y-%m-%dT%H:%M:%SZ','now')),
                   reviewer=?
               WHERE id=?""",
            (reviewer, item_id),
        )
        self.db.commit()

    # -- Phase 8: Daily automation runs --

    def insert_daily_run(self, run: dict) -> str:
        """Record a daily automation run. Returns the run id."""
        from .models import new_id as _new_id
        run_id = run.get("id") or _new_id()
        self.db.execute(
            """INSERT OR REPLACE INTO bt_daily_automation_runs
               (id, profile_name, campaign_id, policy_id, outcome,
                dry_run, error_message, started_at, completed_at, run_date)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                run.get("profile_name", ""),
                run.get("campaign_id", ""),
                run.get("policy_id", ""),
                run.get("outcome", "unknown"),
                1 if run.get("dry_run") else 0,
                run.get("error_message", ""),
                run.get("started_at", ""),
                run.get("completed_at"),
                run.get("run_date", ""),
            ),
        )
        self.db.commit()
        return run_id

    def list_daily_runs(self, run_date: str = "", profile_name: str = "") -> list[dict]:
        """Return daily automation run records."""
        if run_date and profile_name:
            rows = self.db.execute(
                "SELECT * FROM bt_daily_automation_runs WHERE run_date=? AND profile_name=? ORDER BY started_at DESC",
                (run_date, profile_name),
            ).fetchall()
        elif run_date:
            rows = self.db.execute(
                "SELECT * FROM bt_daily_automation_runs WHERE run_date=? ORDER BY started_at DESC",
                (run_date,),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM bt_daily_automation_runs ORDER BY started_at DESC LIMIT 50"
            ).fetchall()
        return [dict(r) for r in rows]

    def has_daily_run_today(self, profile_name: str, run_date: str) -> bool:
        """Check if a daily profile has already run today (non-dry-run)."""
        row = self.db.execute(
            """SELECT COUNT(*) as cnt FROM bt_daily_automation_runs
               WHERE profile_name=? AND run_date=? AND dry_run=0""",
            (profile_name, run_date),
        ).fetchone()
        return (row["cnt"] if row else 0) > 0

    # -- Phase 8: Policy promotion log --

    def log_policy_promotion(self, entry: dict) -> str:
        """Insert a policy promotion/rollback audit log entry."""
        from .models import new_id as _new_id
        entry_id = entry.get("id") or _new_id()
        self.db.execute(
            """INSERT INTO bt_policy_promotion_log
               (id, policy_id, policy_name, event_type, from_state, to_state,
                reason, evidence_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                entry_id,
                entry.get("policy_id", ""),
                entry.get("policy_name", ""),
                entry.get("event_type", ""),
                entry.get("from_state", ""),
                entry.get("to_state", ""),
                entry.get("reason", ""),
                entry.get("evidence_json", "{}"),
            ),
        )
        self.db.commit()
        return entry_id

    def get_policy_promotion_log(self, policy_id: str = "") -> list[dict]:
        """Return promotion log entries, optionally filtered by policy_id."""
        if policy_id:
            rows = self.db.execute(
                "SELECT * FROM bt_policy_promotion_log WHERE policy_id=? ORDER BY created_at DESC",
                (policy_id,),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM bt_policy_promotion_log ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- Phase 10A: Paper segments --

    def save_paper_segment(self, seg: dict) -> None:
        """Insert or replace a paper segment."""
        self.db.execute(
            """INSERT OR REPLACE INTO bt_paper_segments
               (id, paper_id, source_id, segment_index, raw_text,
                compressed_text, relevance_score, domain, status,
                embedding_json, ingested_at, summarized_at, error_message)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                seg["id"], seg["paper_id"], seg.get("source_id", ""),
                seg.get("segment_index", 0), seg.get("raw_text", ""),
                seg.get("compressed_text", ""), seg.get("relevance_score", 0.0),
                seg.get("domain", ""), seg.get("status", "ingested"),
                seg.get("embedding_json"), seg.get("ingested_at", _utcnow()),
                seg.get("summarized_at"), seg.get("error_message", ""),
            ),
        )
        self.db.commit()

    def list_paper_segments(
        self, domain: str = "", status: str = "", paper_id: str = "", limit: int = 100,
    ) -> list[dict]:
        """List paper segments with optional filters."""
        conditions: list[str] = []
        params: list = []
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if paper_id:
            conditions.append("paper_id = ?")
            params.append(paper_id)
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self.db.execute(
            f"SELECT * FROM bt_paper_segments WHERE {where} ORDER BY ingested_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def update_segment_status(self, segment_id: str, status: str, error: str = "") -> None:
        self.db.execute(
            "UPDATE bt_paper_segments SET status=?, error_message=? WHERE id=?",
            (status, error, segment_id),
        )
        self.db.commit()

    def count_paper_segments(self, domain: str = "", status: str = "") -> int:
        conditions: list[str] = []
        params: list = []
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = " AND ".join(conditions) if conditions else "1=1"
        row = self.db.execute(
            f"SELECT COUNT(*) as cnt FROM bt_paper_segments WHERE {where}", params
        ).fetchone()
        return row["cnt"] if row else 0

    # -- Phase 10A: KG entities --

    def save_kg_entity(self, entity: dict) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_kg_entities
               (id, segment_id, paper_id, entity_type, name, canonical_name,
                description, confidence, domain, status, extracted_at, error_message)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                entity["id"], entity["segment_id"], entity.get("paper_id", ""),
                entity.get("entity_type", "concept"), entity["name"],
                entity.get("canonical_name", entity["name"].lower().strip()),
                entity.get("description", ""), entity.get("confidence", 0.5),
                entity.get("domain", ""), entity.get("status", "extracted"),
                entity.get("extracted_at", _utcnow()), entity.get("error_message", ""),
            ),
        )
        self.db.commit()

    def list_kg_entities(
        self, domain: str = "", entity_type: str = "", limit: int = 200,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self.db.execute(
            f"SELECT * FROM bt_kg_entities WHERE {where} ORDER BY confidence DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_kg_entities_for_segment(self, segment_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_kg_entities WHERE segment_id=? ORDER BY confidence DESC",
            (segment_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_entity_canonical_name(self, entity_id: str, canonical_name: str) -> None:
        """Update the canonical_name for an entity (used by canonicalization)."""
        self.db.execute(
            "UPDATE bt_kg_entities SET canonical_name=? WHERE id=?",
            (canonical_name, entity_id),
        )
        self.db.commit()

    # -- Phase 10A: KG relations --

    def save_kg_relation(self, rel: dict) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_kg_relations
               (id, segment_id, paper_id, source_entity_id, target_entity_id,
                relation_type, description, confidence, domain, status,
                extracted_at, error_message)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rel["id"], rel["segment_id"], rel.get("paper_id", ""),
                rel["source_entity_id"], rel["target_entity_id"],
                rel.get("relation_type", "related_to"),
                rel.get("description", ""), rel.get("confidence", 0.5),
                rel.get("domain", ""), rel.get("status", "extracted"),
                rel.get("extracted_at", _utcnow()), rel.get("error_message", ""),
            ),
        )
        self.db.commit()

    def list_kg_relations(
        self, domain: str = "", relation_type: str = "", limit: int = 200,
    ) -> list[dict]:
        conditions: list[str] = []
        params: list = []
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        if relation_type:
            conditions.append("relation_type = ?")
            params.append(relation_type)
        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        rows = self.db.execute(
            f"SELECT * FROM bt_kg_relations WHERE {where} ORDER BY confidence DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_kg_relations_for_entity(self, entity_id: str) -> list[dict]:
        rows = self.db.execute(
            """SELECT * FROM bt_kg_relations
               WHERE source_entity_id=? OR target_entity_id=?
               ORDER BY confidence DESC""",
            (entity_id, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Phase 10A: KG findings (write-back) --

    def save_kg_finding(self, finding: dict) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_kg_findings
               (id, candidate_id, publication_id, title, statement, mechanism,
                domain, confidence, valid_from, valid_until, superseded_by,
                source_evidence_ids, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                finding["id"], finding["candidate_id"],
                finding.get("publication_id", ""),
                finding.get("title", ""), finding.get("statement", ""),
                finding.get("mechanism", ""), finding.get("domain", ""),
                finding.get("confidence", 0.5),
                finding.get("valid_from", _utcnow()),
                finding.get("valid_until"), finding.get("superseded_by"),
                json.dumps(finding.get("source_evidence_ids", [])),
                finding.get("status", "active"),
            ),
        )
        self.db.commit()

    def list_kg_findings(
        self, domain: str = "", status: str = "active", limit: int = 100,
    ) -> list[dict]:
        conditions = ["status = ?"]
        params: list = [status]
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        where = " AND ".join(conditions)
        params.append(limit)
        rows = self.db.execute(
            f"SELECT * FROM bt_kg_findings WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def get_kg_finding(self, finding_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_kg_findings WHERE id=?", (finding_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- Domain candidates --

    def save_domain_candidate(self, c: CandidateSpec) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_domain_candidates
               (id, domain_name, run_id, title, description, parameters,
                rationale, source, parent_id, status, rejection_reason, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.id, c.domain_name, c.run_id, c.title, c.description,
             json.dumps(c.parameters), c.rationale, c.source,
             c.parent_id, c.status.value, c.rejection_reason,
             _iso(c.created_at)),
        )
        self.db.commit()

    def update_domain_candidate_status(
        self, candidate_id: str, status: str, reason: str = "",
    ) -> None:
        self.db.execute(
            "UPDATE bt_domain_candidates SET status=?, rejection_reason=? WHERE id=?",
            (status, reason, candidate_id),
        )
        self.db.commit()

    def list_domain_candidates(
        self, domain_name: str, limit: int = 50,
    ) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_domain_candidates WHERE domain_name=? ORDER BY created_at DESC LIMIT ?",
            (domain_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_domain_candidate(self, candidate_id: str) -> Optional[dict]:
        row = self.db.execute(
            "SELECT * FROM bt_domain_candidates WHERE id=?", (candidate_id,)
        ).fetchone()
        return dict(row) if row else None

    # -- Experiment results --

    def save_experiment_result(self, r: ExperimentRunResult) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_experiment_results
               (id, candidate_id, template_id, domain_name, metrics, raw_data,
                duration_seconds, success, error_message, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (r.id, r.candidate_id, r.template_id, r.domain_name,
             json.dumps(r.metrics), json.dumps(r.raw_data),
             r.duration_seconds, 1 if r.success else 0,
             r.error_message, _iso(r.created_at)),
        )
        self.db.commit()

    def list_experiment_results(
        self, candidate_id: str,
    ) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_experiment_results WHERE candidate_id=? ORDER BY created_at",
            (candidate_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Evaluation results --

    def save_evaluation_result(self, e: EvaluationResult) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_evaluation_results
               (id, candidate_id, domain_name, score_components, final_score,
                hard_fail, hard_fail_reasons, caveats, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (e.id, e.candidate_id, e.domain_name,
             json.dumps(e.score_components), e.final_score,
             1 if e.hard_fail else 0,
             json.dumps(e.hard_fail_reasons), json.dumps(e.caveats),
             _iso(e.created_at)),
        )
        self.db.commit()

    # -- Promotion records --

    def save_promotion_record(self, p: PromotionRecord) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_promotion_records
               (id, candidate_id, domain_name, decision, evaluation_id,
                reason, baseline_score, candidate_score, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (p.id, p.candidate_id, p.domain_name, p.decision.value,
             p.evaluation_id, p.reason, p.baseline_score,
             p.candidate_score, _iso(p.created_at)),
        )
        self.db.commit()

    def list_promotion_records(
        self, domain_name: str, limit: int = 50,
    ) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_promotion_records WHERE domain_name=? ORDER BY created_at DESC LIMIT ?",
            (domain_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Idea memory --

    def save_idea_memory(self, m: IdeaMemoryEntry) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_idea_memory
               (id, domain_name, candidate_id, candidate_title, candidate_family,
                rationale, outcome, lesson, tags, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (m.id, m.domain_name, m.candidate_id, m.candidate_title,
             m.candidate_family, m.rationale, m.outcome, m.lesson,
             json.dumps(m.tags), _iso(m.created_at)),
        )
        self.db.commit()

    def list_idea_memory(
        self, domain_name: str, limit: int = 100,
    ) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_idea_memory WHERE domain_name=? ORDER BY created_at DESC LIMIT ?",
            (domain_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Experiment memory --

    def save_experiment_memory(self, m: ExperimentMemoryEntry) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO bt_experiment_memory
               (id, domain_name, candidate_id, template_name, informative_metrics,
                weakness_exposed, stability_notes, runtime_seconds,
                reproducibility_score, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (m.id, m.domain_name, m.candidate_id, m.template_name,
             json.dumps(m.informative_metrics), m.weakness_exposed,
             m.stability_notes, m.runtime_seconds,
             m.reproducibility_score, _iso(m.created_at)),
        )
        self.db.commit()

    def list_experiment_memory(
        self, domain_name: str, limit: int = 100,
    ) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM bt_experiment_memory WHERE domain_name=? ORDER BY created_at DESC LIMIT ?",
            (domain_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]
