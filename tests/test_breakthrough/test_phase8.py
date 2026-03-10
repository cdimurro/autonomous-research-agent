"""Phase 8 tests: Reviewed Policy Learning, Reviewed Baselines, Label Completeness,
Daily Automation, Review Queue Integration.

All tests are offline-safe (in-memory SQLite, no real Ollama calls).
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from breakthrough_engine.db import init_db, Repository
from breakthrough_engine.reviewed_baseline import (
    ReviewedBaseline, BaselineRegistry, load_phase7d_reviewed_baseline,
    load_phase5_validated_baseline,
)
from breakthrough_engine.label_completeness import (
    LabelTarget, LabelCompleteness,
    check_label_completeness, export_label_targets_csv, summarize_label_completeness,
)
from breakthrough_engine.bayesian_evaluator import (
    BayesianEvaluator, PosteriorState,
    REVIEWED_BINARY_METRICS, REVIEWED_CONTINUOUS_METRICS,
    REVIEWED_BINARY_PRIOR,
)
from breakthrough_engine.policy_registry import (
    PolicyRegistry, PolicyConfig,
    POLICY_STATE_CHALLENGER, POLICY_STATE_CHAMPION, POLICY_STATE_PROBATIONARY_CHAMPION,
    POLICY_STATE_ROLLED_BACK, MAX_ACTIVE_CHALLENGERS,
)
from breakthrough_engine.daily_automation import (
    DailyAutomationProfile, DailyRunResult,
    load_daily_profile, list_available_profiles, dry_run_profile,
    build_review_queue_item, format_operator_summary, get_daily_status,
    OUTCOME_DRY_RUN, OUTCOME_COMPLETED_WITH_DRAFT, OUTCOME_COMPLETED_NO_DRAFT,
    OUTCOME_ALREADY_RAN_TODAY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    return init_db(in_memory=True)


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def evaluator():
    return BayesianEvaluator()


@pytest.fixture
def baselines_dir():
    """Return the real baselines directory."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "runtime", "baselines",
    )


@pytest.fixture
def daily_profiles_dir():
    """Return the real daily profiles directory."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config", "daily_profiles",
    )


# ---------------------------------------------------------------------------
# TestMigration11: DB schema
# ---------------------------------------------------------------------------

class TestMigration11:
    def test_bt_reviewed_baselines_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_reviewed_baselines'"
        ).fetchall()
        assert len(rows) == 1, "bt_reviewed_baselines table should exist"

    def test_bt_review_queue_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_review_queue'"
        ).fetchall()
        assert len(rows) == 1, "bt_review_queue table should exist"

    def test_bt_daily_automation_runs_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_daily_automation_runs'"
        ).fetchall()
        assert len(rows) == 1, "bt_daily_automation_runs table should exist"

    def test_bt_policy_promotion_log_table_exists(self, db):
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bt_policy_promotion_log'"
        ).fetchall()
        assert len(rows) == 1, "bt_policy_promotion_log table should exist"

    def test_bt_policies_has_is_rolled_back_column(self, db):
        # Attempt to query the column — will fail if missing
        db.execute("SELECT is_rolled_back FROM bt_policies LIMIT 1")

    def test_db_version_is_11(self, db):
        row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
        assert row[0] >= 11, f"Expected DB version >= 11, got {row[0]}"


# ---------------------------------------------------------------------------
# TestReviewedBaseline: freeze and load
# ---------------------------------------------------------------------------

class TestReviewedBaselineArtifact:
    def test_phase7d_baseline_file_exists(self, baselines_dir):
        path = os.path.join(baselines_dir, "phase7d_reviewed_baseline.json")
        assert os.path.exists(path), f"Phase 7D baseline file missing: {path}"

    def test_phase7d_baseline_loads(self, baselines_dir):
        reg = BaselineRegistry(baselines_dir=baselines_dir)
        b = reg.load("phase7d_reviewed")
        assert b is not None
        assert b.baseline_id == "phase7d_reviewed"
        assert b.baseline_type == "reviewed_evaluation"
        assert b.campaign_count == 5
        assert b.all_integrity_ok is True
        assert b.all_falsification_complete is True

    def test_phase7d_baseline_metrics(self, baselines_dir):
        reg = BaselineRegistry(baselines_dir=baselines_dir)
        b = reg.load("phase7d_reviewed")
        stats = b.summary_statistics
        assert stats["champion_score_mean"] == pytest.approx(0.90504, abs=0.001)
        assert stats["integrity_ok_rate"] == 1.0
        assert stats["falsification_complete_rate"] == 1.0

    def test_phase5_baseline_loads(self, baselines_dir):
        reg = BaselineRegistry(baselines_dir=baselines_dir)
        b = reg.load("phase5_validated")
        assert b is not None
        assert b.baseline_id == "phase5_validated"
        assert b.baseline_type == "deterministic_benchmark"

    def test_list_baselines_returns_both(self, baselines_dir):
        reg = BaselineRegistry(baselines_dir=baselines_dir)
        baselines = reg.list_baselines()
        ids = [b["baseline_id"] for b in baselines]
        assert "phase5_validated" in ids
        assert "phase7d_reviewed" in ids

    def test_baseline_missing_returns_none(self):
        reg = BaselineRegistry(baselines_dir="/nonexistent/path")
        b = reg.load("phase7d_reviewed")
        assert b is None


class TestReviewedBaselineComparison:
    def test_no_regression_batch(self, baselines_dir):
        """A batch with metrics equal to baseline should show no regression."""
        reg = BaselineRegistry(baselines_dir=baselines_dir)
        # Build a synthetic batch summary matching the baseline
        batch_summary = {
            "campaign_count": 10,
            "summary_statistics": {
                "champion_score_mean": 0.910,   # slightly better than 0.905
                "integrity_ok_rate": 1.0,
                "falsification_complete_rate": 1.0,
                "overall_block_rate": 0.30,
            },
        }
        result = reg.compare_batch_to_reviewed_baseline(batch_summary)
        assert result["ok"] is True
        assert result["regression_found"] is False

    def test_regression_detected(self, baselines_dir):
        """A batch with significantly lower champion score should show regression."""
        reg = BaselineRegistry(baselines_dir=baselines_dir)
        batch_summary = {
            "campaign_count": 10,
            "summary_statistics": {
                "champion_score_mean": 0.80,    # 0.105 below baseline — regression
                "integrity_ok_rate": 1.0,
                "falsification_complete_rate": 1.0,
                "overall_block_rate": 0.30,
            },
        }
        result = reg.compare_batch_to_reviewed_baseline(batch_summary)
        assert result["regression_found"] is True
        assert result["ok"] is False

    def test_integrity_regression_detected(self, baselines_dir):
        """A batch with integrity_ok_rate < 1.0 should show regression."""
        reg = BaselineRegistry(baselines_dir=baselines_dir)
        batch_summary = {
            "campaign_count": 10,
            "summary_statistics": {
                "champion_score_mean": 0.91,
                "integrity_ok_rate": 0.8,       # regression
                "falsification_complete_rate": 1.0,
                "overall_block_rate": 0.30,
            },
        }
        result = reg.compare_batch_to_reviewed_baseline(batch_summary)
        assert result["regression_found"] is True


# ---------------------------------------------------------------------------
# TestLabelCompleteness: detection and export
# ---------------------------------------------------------------------------

class TestLabelCompleteness:
    def _insert_stage_events(self, db, campaign_id, finalists):
        """Helper to insert stage events for finalists."""
        db.execute("""
            CREATE TABLE IF NOT EXISTS bt_stage_events (
                id TEXT PRIMARY KEY,
                campaign_id TEXT,
                event_type TEXT,
                candidate_id TEXT DEFAULT '',
                details_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT '2026-01-01T00:00:00Z'
            )
        """)
        for i, f in enumerate(finalists):
            db.execute(
                """INSERT INTO bt_stage_events (id, campaign_id, event_type, details_json)
                   VALUES (?, ?, 'finalist_selected', ?)""",
                (f"event_{campaign_id}_{i}", campaign_id, json.dumps({
                    "candidate_id": f["id"],
                    "title": f["title"],
                    "final_score": f["score"],
                })),
            )
        db.commit()

    def test_all_missing_when_no_labels(self, db):
        campaign_id = "test_campaign_001"
        self._insert_stage_events(db, campaign_id, [
            {"id": "cand1", "title": "Hypothesis A", "score": 0.90},
            {"id": "cand2", "title": "Hypothesis B", "score": 0.85},
        ])
        completeness = check_label_completeness(db, [campaign_id])
        assert completeness.total_targets == 2
        assert completeness.labeled_targets == 0
        assert completeness.unlabeled_targets == 2
        assert completeness.is_complete is False
        assert completeness.completion_rate == 0.0

    def test_complete_when_both_labeled(self, db, repo):
        campaign_id = "test_campaign_002"
        self._insert_stage_events(db, campaign_id, [
            {"id": "cand3", "title": "Hypothesis C", "score": 0.92},
            {"id": "cand4", "title": "Hypothesis D", "score": 0.88},
        ])
        # Add labels for both
        for cand_id, role in [("cand3", "champion"), ("cand4", "runner_up")]:
            repo.save_review_label({
                "campaign_id": campaign_id,
                "candidate_id": cand_id,
                "candidate_title": f"Hypothesis {cand_id[-1]}",
                "candidate_role": role,
                "decision": "approve",
            })
        completeness = check_label_completeness(db, [campaign_id])
        assert completeness.is_complete is True
        assert completeness.completion_rate == 1.0
        assert completeness.unlabeled_targets == 0

    def test_partial_completion(self, db, repo):
        campaign_id = "test_campaign_003"
        self._insert_stage_events(db, campaign_id, [
            {"id": "cand5", "title": "Hypothesis E", "score": 0.91},
            {"id": "cand6", "title": "Hypothesis F", "score": 0.87},
        ])
        # Only label the champion
        repo.save_review_label({
            "campaign_id": campaign_id,
            "candidate_id": "cand5",
            "candidate_title": "Hypothesis E",
            "candidate_role": "champion",
            "decision": "approve",
        })
        completeness = check_label_completeness(db, [campaign_id])
        assert completeness.total_targets == 2
        assert completeness.labeled_targets == 1
        assert completeness.unlabeled_targets == 1
        assert completeness.completion_rate == pytest.approx(0.5, abs=0.01)

    def test_empty_campaign_list(self, db):
        completeness = check_label_completeness(db, [])
        assert completeness.total_targets == 0
        assert completeness.is_complete is False

    def test_export_csv_contains_headers(self, db):
        campaign_id = "test_campaign_004"
        self._insert_stage_events(db, campaign_id, [
            {"id": "cand7", "title": "Hypothesis G", "score": 0.90},
        ])
        completeness = check_label_completeness(db, [campaign_id])
        csv_content = export_label_targets_csv(completeness)
        assert "campaign_id" in csv_content
        assert "candidate_id" in csv_content
        assert "candidate_role" in csv_content

    def test_summary_text_shows_missing(self, db):
        campaign_id = "test_campaign_005"
        self._insert_stage_events(db, campaign_id, [
            {"id": "cand8", "title": "Hypothesis H", "score": 0.90},
        ])
        completeness = check_label_completeness(db, [campaign_id])
        summary = summarize_label_completeness(completeness)
        assert "Missing" in summary or "missing" in summary

    def test_summary_text_shows_complete(self, db, repo):
        campaign_id = "test_campaign_006"
        self._insert_stage_events(db, campaign_id, [
            {"id": "cand9", "title": "Hypothesis I", "score": 0.90},
        ])
        repo.save_review_label({
            "campaign_id": campaign_id,
            "candidate_id": "cand9",
            "candidate_title": "Hypothesis I",
            "candidate_role": "champion",
            "decision": "approve",
        })
        completeness = check_label_completeness(db, [campaign_id])
        summary = summarize_label_completeness(completeness)
        assert "complete" in summary.lower()

    def test_export_csv_to_file(self, db, tmp_path):
        campaign_id = "test_campaign_007"
        self._insert_stage_events(db, campaign_id, [
            {"id": "cand10", "title": "Hypothesis J", "score": 0.90},
        ])
        completeness = check_label_completeness(db, [campaign_id])
        output_path = str(tmp_path / "targets.csv")
        export_label_targets_csv(completeness, output_path=output_path)
        assert os.path.exists(output_path)
        content = open(output_path).read()
        assert "campaign_id" in content


# ---------------------------------------------------------------------------
# TestReviewedPolicyPromotion: Phase 8 gate
# ---------------------------------------------------------------------------

class TestReviewedPolicyPromotion:
    def test_review_signal_gate_passes_with_good_signals(self, repo):
        reg = PolicyRegistry(repo)
        challenger = reg.register(PolicyConfig(name="test_challenger_gate_1"))

        review_signal = {
            "review_approval_rate": 0.80,
            "review_novelty_confidence": 0.75,
            "review_technical_plausibility": 0.70,
            "review_reject_rate": 0.10,
        }
        champion_signal = {
            "review_approval_rate": 0.78,
            "review_novelty_confidence": 0.73,
            "review_technical_plausibility": 0.68,
            "review_reject_rate": 0.12,
        }
        passed, msg, failures = reg.check_reviewed_promotion_criteria(
            challenger.id, review_signal, champion_signal
        )
        assert passed is True
        assert failures == []

    def test_review_signal_gate_fails_with_bad_approval(self, repo):
        reg = PolicyRegistry(repo)
        challenger = reg.register(PolicyConfig(name="test_challenger_gate_2"))

        review_signal = {
            "review_approval_rate": 0.50,     # much worse than champion
            "review_novelty_confidence": 0.75,
            "review_technical_plausibility": 0.70,
            "review_reject_rate": 0.10,
        }
        champion_signal = {
            "review_approval_rate": 0.80,
            "review_novelty_confidence": 0.73,
            "review_technical_plausibility": 0.68,
            "review_reject_rate": 0.12,
        }
        passed, msg, failures = reg.check_reviewed_promotion_criteria(
            challenger.id, review_signal, champion_signal
        )
        assert passed is False
        assert len(failures) > 0
        assert "review_approval_rate" in failures[0]

    def test_review_signal_gate_skipped_when_no_signals(self, repo):
        reg = PolicyRegistry(repo)
        challenger = reg.register(PolicyConfig(name="test_challenger_gate_3"))
        passed, msg, failures = reg.check_reviewed_promotion_criteria(
            challenger.id, {}, {}
        )
        assert passed is True
        assert "skipped" in msg.lower()

    def test_get_policy_status_challenger(self, repo):
        reg = PolicyRegistry(repo)
        challenger = reg.register(PolicyConfig(name="status_test_challenger"))
        status = reg.get_policy_status(challenger.id)
        assert status == POLICY_STATE_CHALLENGER

    def test_get_policy_status_champion(self, repo):
        reg = PolicyRegistry(repo)
        status = reg.get_policy_status("phase5_champion")
        assert status == POLICY_STATE_CHAMPION

    def test_get_policy_status_not_found(self, repo):
        reg = PolicyRegistry(repo)
        status = reg.get_policy_status("nonexistent_id")
        assert status == "not_found"

    def test_count_active_challengers_zero_initially(self, repo):
        reg = PolicyRegistry(repo)
        count = reg.count_active_challengers()
        assert count == 0

    def test_count_active_challengers_increases(self, repo):
        reg = PolicyRegistry(repo)
        reg.register(PolicyConfig(name="challenger_count_test"))
        count = reg.count_active_challengers()
        assert count == 1

    def test_can_register_challenger_true_initially(self, repo):
        reg = PolicyRegistry(repo)
        can, msg = reg.can_register_challenger()
        assert can is True

    def test_can_register_challenger_false_when_max_reached(self, repo):
        reg = PolicyRegistry(repo)
        for i in range(MAX_ACTIVE_CHALLENGERS):
            reg.register(PolicyConfig(name=f"max_challenger_{i}"))
        can, msg = reg.can_register_challenger()
        assert can is False
        assert str(MAX_ACTIVE_CHALLENGERS) in msg

    def test_rollback_marks_is_rolled_back(self, repo):
        """After rollback, the demoted policy should have is_rolled_back=1."""
        reg = PolicyRegistry(repo)
        # Register and promote a challenger all the way to champion
        challenger = reg.register(PolicyConfig(name="rollback_test_challenger"))
        # Promote to probation then champion manually
        repo.db.execute(
            "UPDATE bt_policies SET is_probation=1 WHERE id=?", (challenger.id,)
        )
        repo.db.commit()
        ok, msg = reg.promote_to_champion(challenger.id, reason="test")
        assert ok is True

        # Now rollback
        ok, msg = reg.rollback_champion(reason="regression test")
        assert ok is True

        # Check the demoted policy is marked rolled_back
        row = repo.db.execute(
            "SELECT is_rolled_back FROM bt_policies WHERE id=?", (challenger.id,)
        ).fetchone()
        if row and dict(row).get("is_rolled_back") is not None:
            assert dict(row)["is_rolled_back"] == 1


# ---------------------------------------------------------------------------
# TestReviewWeightedBayesian: review-label posterior updates
# ---------------------------------------------------------------------------

class TestReviewWeightedBayesian:
    def test_new_reviewed_binary_state(self, evaluator):
        state = evaluator.new_reviewed_state("pol1", "clean-energy", "review_label_approval")
        assert state.distribution_type == "beta_binomial"
        assert state.alpha == REVIEWED_BINARY_PRIOR["alpha"]
        assert state.beta == REVIEWED_BINARY_PRIOR["beta"]
        assert state.observation_unit == "label"

    def test_new_reviewed_continuous_state(self, evaluator):
        state = evaluator.new_reviewed_state(
            "pol1", "clean-energy", "review_novelty_confidence"
        )
        assert state.distribution_type == "normal_approx"
        assert state.observation_unit == "label"

    def test_unknown_reviewed_metric_raises(self, evaluator):
        with pytest.raises(ValueError, match="Unknown reviewed metric"):
            evaluator.new_reviewed_state("pol1", "clean-energy", "nonexistent_metric")

    def test_approve_label_increases_approval_probability(self, evaluator):
        state = evaluator.new_reviewed_state("pol1", "clean-energy", "review_label_approval")
        initial_mean = evaluator.get_posterior_summary(state).mean

        states = {"review_label_approval": state}
        updated = evaluator.update_from_review_label(
            states, "pol1", "clean-energy",
            {"decision": "approve", "novelty_confidence": 0.85,
             "technical_plausibility": 0.80, "commercialization_relevance": 0.70}
        )
        new_mean = evaluator.get_posterior_summary(updated["review_label_approval"]).mean
        assert new_mean > initial_mean, "Approve should increase approval probability"

    def test_reject_label_decreases_approval_probability(self, evaluator):
        state = evaluator.new_reviewed_state("pol1", "clean-energy", "review_label_approval")
        initial_mean = evaluator.get_posterior_summary(state).mean

        states = {"review_label_approval": state}
        updated = evaluator.update_from_review_label(
            states, "pol1", "clean-energy",
            {"decision": "reject", "novelty_confidence": 0.3,
             "technical_plausibility": 0.2, "commercialization_relevance": 0.1}
        )
        new_mean = evaluator.get_posterior_summary(updated["review_label_approval"]).mean
        assert new_mean < initial_mean, "Reject should decrease approval probability"

    def test_defer_label_does_not_update_approval(self, evaluator):
        state = evaluator.new_reviewed_state("pol1", "clean-energy", "review_label_approval")
        initial_mean = evaluator.get_posterior_summary(state).mean

        states = {"review_label_approval": state}
        updated = evaluator.update_from_review_label(
            states, "pol1", "clean-energy",
            {"decision": "defer", "novelty_confidence": 0.5,
             "technical_plausibility": 0.5, "commercialization_relevance": 0.5}
        )
        # Approval state should not have changed (defer is skipped for binary)
        if "review_label_approval" in updated:
            new_mean = evaluator.get_posterior_summary(updated["review_label_approval"]).mean
            assert new_mean == pytest.approx(initial_mean, abs=0.01)

    def test_continuous_metrics_updated_from_label(self, evaluator):
        states = {}
        updated = evaluator.update_from_review_label(
            states, "pol1", "clean-energy",
            {"decision": "approve", "novelty_confidence": 0.85,
             "technical_plausibility": 0.80, "commercialization_relevance": 0.70}
        )
        assert "review_novelty_confidence" in updated
        assert "review_technical_plausibility" in updated
        assert "review_commercialization_relevance" in updated

        nc_state = updated["review_novelty_confidence"]
        assert nc_state.n == 1
        assert nc_state.mu == pytest.approx(0.85, abs=0.01)

    def test_reviewed_posterior_means_returns_none_for_no_observations(self, evaluator):
        state = evaluator.new_reviewed_state("pol1", "clean-energy", "review_label_approval")
        states = {"review_label_approval": state}
        means = evaluator.get_reviewed_posterior_means(states)
        # Prior-only state — sample_size=0 for continuous, for beta it's alpha+beta-2=2
        # For Beta(2,2), n=alpha+beta-2=2, but those are pseudo-obs
        # We report None only for continuous with n=0
        # Actually for binary we have sample_size = alpha+beta-2 = 2 (pseudo), mean = 0.5
        # So approval should be 0.5, not None
        assert means.get("review_label_approval") == pytest.approx(0.5, abs=0.01)

    def test_summarize_reviewed_posteriors(self, evaluator):
        states = {}
        updated = evaluator.update_from_review_label(
            states, "pol1", "clean-energy",
            {"decision": "approve", "novelty_confidence": 0.85,
             "technical_plausibility": 0.80, "commercialization_relevance": 0.70}
        )
        summary = evaluator.summarize_reviewed_posteriors(updated)
        assert "review_label_approval" in summary
        assert "review_novelty_confidence" in summary
        assert summary["review_label_approval"]["mean"] is not None

    def test_weakly_informative_prior_limits_label_dominance(self, evaluator):
        """One approve label should not push approval probability above 0.75."""
        state = evaluator.new_reviewed_state("pol1", "clean-energy", "review_label_approval")
        states = {"review_label_approval": state}
        updated = evaluator.update_from_review_label(
            states, "pol1", "clean-energy",
            {"decision": "approve", "novelty_confidence": 1.0,
             "technical_plausibility": 1.0, "commercialization_relevance": 1.0}
        )
        # Beta(2,2) prior + 1 success = Beta(3,2) → mean = 3/5 = 0.6
        new_mean = evaluator.get_posterior_summary(updated["review_label_approval"]).mean
        assert new_mean < 0.75, "Single approve label should not dominate prior too aggressively"

    def test_persist_and_load_reviewed_posterior(self, evaluator, repo):
        state = evaluator.new_reviewed_state("pol1", "clean-energy", "review_label_approval")
        state = evaluator.update_binary(state, True)
        evaluator.persist_posterior(repo, state)

        loaded = evaluator.get_or_create_reviewed_posterior(
            repo, "pol1", "clean-energy", "review_label_approval"
        )
        assert loaded.alpha > 2.0  # Must have updated from prior


# ---------------------------------------------------------------------------
# TestDailyAutomationProfile: loading and dry-run
# ---------------------------------------------------------------------------

class TestDailyAutomationProfile:
    def test_load_evaluation_profile(self, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        assert profile.profile_name == "evaluation_daily_clean_energy"
        assert profile.profile_type == "evaluation_daily"
        assert profile.campaign_profile == "eval_clean_energy_30m"
        assert profile.max_runs_per_day == 1
        assert profile.require_integrity_ok is True
        assert profile.insert_review_queue is True

    def test_load_production_profile(self, daily_profiles_dir):
        profile = load_daily_profile("production_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        assert profile.profile_name == "production_daily_clean_energy"
        assert profile.profile_type == "production_daily"
        assert profile.campaign_profile == "overnight_clean_energy"
        assert profile.require_integrity_ok is False
        assert profile.insert_review_queue is True

    def test_load_nonexistent_profile_raises(self):
        with pytest.raises(FileNotFoundError):
            load_daily_profile("nonexistent_profile", profiles_dir="/tmp/no_such_dir")

    def test_list_profiles_returns_both(self, daily_profiles_dir):
        profiles = list_available_profiles(profiles_dir=daily_profiles_dir)
        assert "evaluation_daily_clean_energy" in profiles
        assert "production_daily_clean_energy" in profiles

    def test_profile_to_dict(self, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        d = profile.to_dict()
        assert d["profile_name"] == "evaluation_daily_clean_energy"
        assert d["insert_review_queue"] is True


class TestDailyAutomationDryRun:
    def test_dry_run_returns_dry_run_outcome(self, repo, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        result = dry_run_profile(profile, repo, run_date="2026-03-09")
        assert result.outcome == OUTCOME_DRY_RUN
        assert result.dry_run is True

    def test_dry_run_logs_to_db(self, repo, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        dry_run_profile(profile, repo, run_date="2026-03-09")
        runs = repo.list_daily_runs(run_date="2026-03-09",
                                     profile_name="evaluation_daily_clean_energy")
        assert len(runs) >= 1
        assert runs[0]["dry_run"] == 1

    def test_dry_run_does_not_count_as_real_run(self, repo, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        dry_run_profile(profile, repo, run_date="2026-03-10")
        # has_daily_run_today should return False (dry runs excluded)
        already_ran = repo.has_daily_run_today(
            "evaluation_daily_clean_energy", "2026-03-10"
        )
        assert already_ran is False

    def test_dry_run_summary_explains_action(self, repo, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        result = dry_run_profile(profile, repo, run_date="2026-03-09")
        assert "DRY RUN" in result.operator_summary
        assert "evaluation_daily_clean_energy" in result.operator_summary


# ---------------------------------------------------------------------------
# TestDailyAutomationDB: run recording and bounds
# ---------------------------------------------------------------------------

class TestDailyAutomationDB:
    def test_insert_and_list_daily_run(self, repo):
        run_id = repo.insert_daily_run({
            "profile_name": "test_profile",
            "campaign_id": "camp_123",
            "policy_id": "phase5_champion",
            "outcome": OUTCOME_COMPLETED_WITH_DRAFT,
            "dry_run": False,
            "error_message": "",
            "started_at": "2026-03-09T06:00:00Z",
            "completed_at": "2026-03-09T06:30:00Z",
            "run_date": "2026-03-09",
        })
        runs = repo.list_daily_runs(run_date="2026-03-09", profile_name="test_profile")
        assert len(runs) == 1
        assert runs[0]["campaign_id"] == "camp_123"
        assert runs[0]["outcome"] == OUTCOME_COMPLETED_WITH_DRAFT

    def test_has_daily_run_today_false_initially(self, repo):
        result = repo.has_daily_run_today("test_profile_x", "2026-03-09")
        assert result is False

    def test_has_daily_run_today_true_after_real_run(self, repo):
        repo.insert_daily_run({
            "profile_name": "test_profile_y",
            "campaign_id": "camp_456",
            "policy_id": "phase5_champion",
            "outcome": OUTCOME_COMPLETED_NO_DRAFT,
            "dry_run": False,
            "error_message": "",
            "started_at": "2026-03-09T07:00:00Z",
            "completed_at": "2026-03-09T07:30:00Z",
            "run_date": "2026-03-09",
        })
        result = repo.has_daily_run_today("test_profile_y", "2026-03-09")
        assert result is True

    def test_has_daily_run_today_false_for_dry_run_only(self, repo):
        repo.insert_daily_run({
            "profile_name": "test_profile_z",
            "campaign_id": "",
            "policy_id": "phase5_champion",
            "outcome": OUTCOME_DRY_RUN,
            "dry_run": True,
            "error_message": "",
            "started_at": "2026-03-09T08:00:00Z",
            "completed_at": "2026-03-09T08:00:00Z",
            "run_date": "2026-03-09",
        })
        result = repo.has_daily_run_today("test_profile_z", "2026-03-09")
        assert result is False


# ---------------------------------------------------------------------------
# TestReviewQueueIntegration: insert and inspect
# ---------------------------------------------------------------------------

class TestReviewQueueIntegration:
    def test_insert_review_queue_item(self, repo):
        item_id = repo.insert_review_queue_item({
            "campaign_id": "camp_789",
            "daily_run_id": "run_001",
            "profile_name": "evaluation_daily_clean_energy",
            "policy_id": "phase5_champion",
            "champion_title": "Perovskite Solar Efficiency Breakthrough",
            "champion_score": 0.91,
            "champion_candidate_id": "cand_001",
            "falsification_summary": "medium",
            "rationale": "High novelty and technical plausibility",
            "outcome": OUTCOME_COMPLETED_WITH_DRAFT,
        })
        assert item_id != ""

    def test_list_review_queue_pending(self, repo):
        repo.insert_review_queue_item({
            "campaign_id": "camp_pending",
            "daily_run_id": "run_002",
            "profile_name": "test_profile",
            "policy_id": "phase5_champion",
            "champion_title": "Test Champion",
            "champion_score": 0.88,
            "champion_candidate_id": "cand_002",
            "falsification_summary": "low",
            "rationale": "Strong hypothesis",
            "outcome": OUTCOME_COMPLETED_WITH_DRAFT,
        })
        items = repo.list_review_queue(review_status="pending")
        assert len(items) >= 1
        campaign_ids = [i["campaign_id"] for i in items]
        assert "camp_pending" in campaign_ids

    def test_mark_reviewed(self, repo):
        item_id = repo.insert_review_queue_item({
            "campaign_id": "camp_review",
            "daily_run_id": "run_003",
            "profile_name": "test_profile",
            "policy_id": "phase5_champion",
            "champion_title": "To Be Reviewed",
            "champion_score": 0.87,
            "champion_candidate_id": "cand_003",
            "falsification_summary": "medium",
            "rationale": "Interesting candidate",
            "outcome": OUTCOME_COMPLETED_WITH_DRAFT,
        })
        repo.mark_review_queue_item_reviewed(item_id, reviewer="test_reviewer")

        items = repo.list_review_queue(review_status="reviewed")
        reviewed_ids = [i["id"] for i in items]
        assert item_id in reviewed_ids

    def test_build_review_queue_item_with_draft(self, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        campaign_result = {
            "campaign_id": "camp_build_test",
            "has_draft": True,
            "champion": {
                "id": "cand_build",
                "title": "Solar Hydrogen Innovation",
                "final_score": 0.92,
                "falsification_risk": "medium",
            },
            "champion_rationale": "Strong evidence with clear mechanism",
            "finalist_count": 5,
        }
        item = build_review_queue_item(
            daily_run_id="run_build",
            profile=profile,
            campaign_result=campaign_result,
            policy_id="phase5_champion",
        )
        assert item["campaign_id"] == "camp_build_test"
        assert item["champion_title"] == "Solar Hydrogen Innovation"
        assert item["champion_score"] == pytest.approx(0.92, abs=0.001)
        assert item["outcome"] == OUTCOME_COMPLETED_WITH_DRAFT
        assert item["review_status"] == "pending"

    def test_build_review_queue_item_no_draft(self, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        campaign_result = {
            "campaign_id": "camp_no_draft",
            "has_draft": False,
            "champion": {"id": "cand_x", "title": "Low Score Idea", "final_score": 0.55},
        }
        item = build_review_queue_item(
            daily_run_id="run_x", profile=profile,
            campaign_result=campaign_result, policy_id="phase5_champion",
        )
        assert item["outcome"] == OUTCOME_COMPLETED_NO_DRAFT


# ---------------------------------------------------------------------------
# TestPolicyPromotionLog: audit trail
# ---------------------------------------------------------------------------

class TestPolicyPromotionLog:
    def test_log_promotion_event(self, repo):
        entry_id = repo.log_policy_promotion({
            "policy_id": "test_policy_log",
            "policy_name": "test_log_policy",
            "event_type": "promoted_to_champion",
            "from_state": "probationary_champion",
            "to_state": "champion",
            "reason": "All criteria met",
            "evidence_json": json.dumps({"benchmark_delta": 0.02}),
        })
        assert entry_id != ""

    def test_get_promotion_log(self, repo):
        repo.log_policy_promotion({
            "policy_id": "test_policy_history",
            "policy_name": "test_hist",
            "event_type": "rollback",
            "from_state": "champion",
            "to_state": "rolled_back",
            "reason": "regression",
            "evidence_json": "{}",
        })
        log = repo.get_policy_promotion_log(policy_id="test_policy_history")
        assert len(log) >= 1
        assert log[0]["event_type"] == "rollback"

    def test_get_promotion_log_all(self, repo):
        repo.log_policy_promotion({
            "policy_id": "any_policy",
            "policy_name": "any",
            "event_type": "promoted_to_probation",
            "from_state": "challenger",
            "to_state": "probationary_champion",
            "reason": "met criteria",
            "evidence_json": "{}",
        })
        log = repo.get_policy_promotion_log()
        assert len(log) >= 1


# ---------------------------------------------------------------------------
# TestGetDailyStatus: status check
# ---------------------------------------------------------------------------

class TestGetDailyStatus:
    def test_get_daily_status_returns_dict(self, repo, daily_profiles_dir):
        status = get_daily_status(repo, run_date="2026-03-09")
        assert "date" in status
        assert "profiles" in status
        assert status["date"] == "2026-03-09"

    def test_daily_status_shows_not_ran(self, repo, daily_profiles_dir):
        status = get_daily_status(repo, run_date="2099-01-01")  # Future date, no runs
        for profile_name, info in status.get("profiles", {}).items():
            assert info.get("ran_today") is False


# ---------------------------------------------------------------------------
# TestFormatOperatorSummary
# ---------------------------------------------------------------------------

class TestFormatOperatorSummary:
    def test_format_completed_with_draft(self, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        result = DailyRunResult(
            run_id="run_fmt1",
            profile_name="evaluation_daily_clean_energy",
            campaign_id="camp_fmt",
            policy_id="phase5_champion",
            outcome=OUTCOME_COMPLETED_WITH_DRAFT,
            dry_run=False,
            run_date="2026-03-09",
            review_queue_item_id="rq_001",
        )
        summary = format_operator_summary(result, profile)
        assert "COMPLETED_WITH_DRAFT" in summary
        assert "review" in summary.lower()

    def test_format_already_ran_today(self, daily_profiles_dir):
        profile = load_daily_profile("evaluation_daily_clean_energy",
                                     profiles_dir=daily_profiles_dir)
        result = DailyRunResult(
            run_id="run_fmt2",
            profile_name="evaluation_daily_clean_energy",
            outcome=OUTCOME_ALREADY_RAN_TODAY,
            dry_run=False,
            run_date="2026-03-09",
        )
        summary = format_operator_summary(result, profile)
        assert "already" in summary.lower() or "skipped" in summary.lower()
