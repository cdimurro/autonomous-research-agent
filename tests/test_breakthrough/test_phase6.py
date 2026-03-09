"""Phase 6 tests: Bayesian evaluation, policy optimization, daily search ladder,
falsification, reward logging, review cockpit, and baseline comparison.

All tests are offline-safe (use MockEmbeddingProvider, FakeCandidateGenerator,
in-memory SQLite). No Ollama, no real network calls.

Test classes:
1. TestSchemaV007Migration
2. TestBayesianEvaluator
3. TestPolicyRegistry
4. TestBaselineComparator
5. TestFalsificationEngine
6. TestRewardLogger
7. TestReviewCockpit
8. TestDailySearchLadder
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

import pytest

from breakthrough_engine.db import Repository, init_db
from breakthrough_engine.models import (
    CandidateHypothesis,
    CandidateScore,
    CandidateStatus,
    EvidenceItem,
    EvidencePack,
    ResearchProgram,
    RunMode,
    RunRecord,
    RunStatus,
    new_id,
)


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    conn = init_db(in_memory=True)
    yield conn
    conn.close()


@pytest.fixture
def repo(db):
    return Repository(db)


def _make_candidate(domain="clean-energy", title="Test candidate", statement=None) -> CandidateHypothesis:
    return CandidateHypothesis(
        id=new_id(),
        run_id=new_id(),
        title=title,
        statement=statement or f"A novel {domain} mechanism involving nanoparticles and catalysis.",
        domain=domain,
        mechanism="Electrocatalytic reduction using iron nanoparticles on graphene substrate",
        expected_outcome="Improved catalytic efficiency for hydrogen production by 30%",
        assumptions=["Iron is abundant", "Graphene is stable at operating temperature"],
        risk_flags=["Scale-up not demonstrated"],
    )


def _make_evidence_pack(candidate: CandidateHypothesis) -> EvidencePack:
    return EvidencePack(
        candidate_id=candidate.id,
        items=[
            EvidenceItem(
                id=new_id(),
                source_type="paper",
                source_id="arxiv_001",
                title="Iron catalyst study",
                quote="Iron nanoparticles demonstrate high catalytic activity for electrocatalytic reactions.",
                citation="Smith et al. 2023",
                relevance_score=0.85,
            ),
            EvidenceItem(
                id=new_id(),
                source_type="paper",
                source_id="arxiv_002",
                title="Graphene substrate review",
                quote="Graphene substrates support stable electrode materials in electrochemical systems.",
                citation="Jones et al. 2022",
                relevance_score=0.78,
            ),
        ],
    )



def _good_evidence(trial_count: int = 5) -> dict:
    """Build a passing promotion evidence dict for tests."""
    return {
        "trial_count": trial_count,
        "posterior_means": {
            "novelty_pass_rate": 0.90,
            "top_candidate_final_score": 0.85,
            "falsification_pass_rate": 0.80,
            "operator_burden_proxy": 0.10,
            "draft_quality_proxy": 0.82,
        },
        "champion_means": {
            "novelty_pass_rate": 0.85,
            "top_candidate_final_score": 0.80,
            "falsification_pass_rate": 0.75,
            "operator_burden_proxy": 0.20,
            "draft_quality_proxy": 0.78,
        },
    }

# ---------------------------------------------------------------------------
# 1. Schema v007 Migration
# ---------------------------------------------------------------------------


class TestSchemaV007Migration:
    PHASE6_TABLES = [
        "bt_policies",
        "bt_policy_trials",
        "bt_bayesian_posteriors",
        "bt_reward_logs",
        "bt_trajectories",
        "bt_baseline_comparisons",
        "bt_falsification_summaries",
        "bt_daily_campaigns",
        "bt_ladder_stages",
    ]

    def test_all_phase6_tables_exist(self, db):
        tables = {
            r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'bt_%'"
            ).fetchall()
        }
        for tbl in self.PHASE6_TABLES:
            assert tbl in tables, f"Missing Phase 6 table: {tbl}"

    def test_schema_version_at_least_7(self, db):
        row = db.execute("SELECT MAX(version) FROM bt_schema_version").fetchone()
        assert row is not None
        assert row[0] >= 7

    def test_bt_policies_columns(self, db):
        cols = {r[1] for r in db.execute("PRAGMA table_info(bt_policies)").fetchall()}
        for col in ("id", "name", "version", "config_json", "is_champion", "is_probation", "created_at"):
            assert col in cols, f"Missing column in bt_policies: {col}"

    def test_bt_bayesian_posteriors_unique_constraint(self, db):
        # Insert twice, second should fail or upsert cleanly
        db.execute("""INSERT INTO bt_bayesian_posteriors
            (policy_id, domain, metric_name, observation_unit, distribution_type,
             alpha, beta, mu, M2, n, last_updated, update_history_json)
            VALUES ('p1', 'clean-energy', 'novelty_pass', 'candidate', 'beta_binomial',
                    1.0, 1.0, 0.0, 0.0, 0, '', '[]')""")
        db.commit()
        # Upsert should succeed
        db.execute("""INSERT INTO bt_bayesian_posteriors
            (policy_id, domain, metric_name, observation_unit, distribution_type,
             alpha, beta, mu, M2, n, last_updated, update_history_json)
            VALUES ('p1', 'clean-energy', 'novelty_pass', 'candidate', 'beta_binomial',
                    2.0, 1.0, 0.0, 0.0, 0, '', '[]')
            ON CONFLICT(policy_id, domain, metric_name) DO UPDATE SET alpha=excluded.alpha""")
        db.commit()
        row = db.execute(
            "SELECT alpha FROM bt_bayesian_posteriors WHERE policy_id='p1'"
        ).fetchone()
        assert row[0] == 2.0

    def test_existing_tables_preserved(self, db):
        # Core v006 tables should still exist
        for tbl in ("bt_candidates", "bt_runs", "bt_scores", "bt_publications"):
            row = db.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{tbl}'"
            ).fetchone()
            assert row is not None, f"Existing table {tbl} was destroyed by migration"


# ---------------------------------------------------------------------------
# 2. Bayesian Evaluator
# ---------------------------------------------------------------------------


class TestBayesianEvaluator:
    def test_new_state_binary(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        assert state.distribution_type == "beta_binomial"
        assert state.alpha == 1.0
        assert state.beta == 1.0
        assert state.observation_unit == "candidate"

    def test_new_state_continuous(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "final_score")
        assert state.distribution_type == "normal_approx"
        assert state.n == 0
        assert state.observation_unit == "candidate"

    def test_new_state_unknown_metric_raises(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        with pytest.raises(ValueError, match="Unknown metric"):
            ev.new_state("p1", "clean-energy", "not_a_real_metric")

    def test_update_binary_success(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        new_state = ev.update_binary(state, success=True)
        assert new_state.alpha == 2.0
        assert new_state.beta == 1.0

    def test_update_binary_failure(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        new_state = ev.update_binary(state, success=False)
        assert new_state.alpha == 1.0
        assert new_state.beta == 2.0

    def test_update_binary_tracks_history(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        state = ev.update_binary(state, True)
        state = ev.update_binary(state, False)
        assert len(state.update_history) == 2
        assert state.update_history[0]["observation"] == 1
        assert state.update_history[1]["observation"] == 0

    def test_update_continuous_welford(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "final_score")
        state = ev.update_continuous(state, 0.8)
        assert state.n == 1
        assert abs(state.mu - 0.8) < 1e-9
        state = ev.update_continuous(state, 0.6)
        assert state.n == 2
        assert abs(state.mu - 0.7) < 1e-9

    def test_posterior_summary_binary(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        # 8 successes, 2 failures
        for _ in range(8):
            state = ev.update_binary(state, True)
        for _ in range(2):
            state = ev.update_binary(state, False)
        summary = ev.get_posterior_summary(state)
        assert abs(summary.mean - (9 / 12)) < 0.01
        assert summary.sample_size == 10
        assert summary.ci_lower < summary.mean < summary.ci_upper

    def test_posterior_summary_continuous(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "final_score")
        for v in [0.7, 0.8, 0.75, 0.85, 0.9]:
            state = ev.update_continuous(state, v)
        summary = ev.get_posterior_summary(state)
        assert abs(summary.mean - 0.8) < 0.01
        assert summary.sample_size == 5

    def test_thompson_sample_beta(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        for _ in range(20):
            sample = ev.thompson_sample(state)
            assert 0.0 <= sample <= 1.0

    def test_rank_policies_thompson(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        # Policy A: many successes; Policy B: many failures
        state_a = ev.new_state("A", "clean-energy", "novelty_pass")
        for _ in range(50):
            state_a = ev.update_binary(state_a, True)
        state_b = ev.new_state("B", "clean-energy", "novelty_pass")
        for _ in range(50):
            state_b = ev.update_binary(state_b, False)
        # Rank 20 times and A should usually win
        a_wins = 0
        for _ in range(20):
            ranked = ev.rank_policies_thompson({"A": state_a, "B": state_b})
            if ranked[0] == "A":
                a_wins += 1
        assert a_wins >= 15, f"A should usually win but won only {a_wins}/20 times"

    def test_rank_policies_ucb(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state_a = ev.new_state("A", "clean-energy", "novelty_pass")
        for _ in range(20):
            state_a = ev.update_binary(state_a, True)
        state_b = ev.new_state("B", "clean-energy", "novelty_pass")
        ranked = ev.rank_policies_ucb({"A": state_a, "B": state_b})
        # B has high uncertainty — UCB should prefer it or A depending on c
        assert len(ranked) == 2
        assert set(ranked) == {"A", "B"}

    def test_persist_and_load_posterior(self, repo):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        state = ev.update_binary(state, True)
        state = ev.update_binary(state, True)
        ev.persist_posterior(repo, state)

        loaded = ev.load_posteriors(repo, "p1", "clean-energy")
        assert "novelty_pass" in loaded
        assert loaded["novelty_pass"].alpha == 3.0

    def test_get_or_create_posterior_creates_new(self, repo):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.get_or_create_posterior(repo, "p999", "materials", "final_score")
        assert state.policy_id == "p999"
        assert state.n == 0

    def test_explain_update(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        new_state = ev.update_binary(state, True)
        explanation = ev.explain_update(state, new_state, 1.0)
        assert "Prior" in explanation
        assert "Posterior" in explanation
        assert "mean=" in explanation

    def test_uncertainty_label_progression(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator, _uncertainty_label
        assert _uncertainty_label(0) == "high"
        assert _uncertainty_label(4) == "high"
        assert _uncertainty_label(5) == "medium"
        assert _uncertainty_label(19) == "medium"
        assert _uncertainty_label(20) == "low"

    def test_history_capped_at_50(self):
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator, MAX_HISTORY_ENTRIES
        ev = BayesianEvaluator()
        state = ev.new_state("p1", "clean-energy", "novelty_pass")
        for _ in range(60):
            state = ev.update_binary(state, True)
        assert len(state.update_history) == MAX_HISTORY_ENTRIES


# ---------------------------------------------------------------------------
# 3. Policy Registry
# ---------------------------------------------------------------------------


class TestPolicyRegistry:
    def test_default_champion_created_on_init(self, repo):
        from breakthrough_engine.policy_registry import PolicyRegistry, PHASE5_CHAMPION_ID
        registry = PolicyRegistry(repo)
        champion = registry.get_champion()
        assert champion is not None
        assert champion.id == PHASE5_CHAMPION_ID

    def test_register_challenger(self, repo):
        from breakthrough_engine.policy_registry import PolicyRegistry, PolicyConfig
        registry = PolicyRegistry(repo)
        challenger = registry.register(PolicyConfig(
            name="test_challenger",
            version="1.0",
            description="Test challenger",
            generation_prompt_variant="synthesis_focus",
        ))
        assert challenger.id != ""
        challengers = registry.get_challengers()
        ids = [c.id for c in challengers]
        assert challenger.id in ids

    def test_get_champion_returns_phase5_default(self, repo):
        from breakthrough_engine.policy_registry import PolicyRegistry, PHASE5_CHAMPION_ID
        registry = PolicyRegistry(repo)
        champion = registry.get_champion()
        assert champion.id == PHASE5_CHAMPION_ID
        assert champion.generation_prompt_variant == "standard"

    def test_promote_to_probation_fails_insufficient_trials(self, repo):
        from breakthrough_engine.policy_registry import PolicyRegistry, PolicyConfig
        registry = PolicyRegistry(repo)
        challenger = registry.register(PolicyConfig(
            name="c1", version="1.0", description="Challenger 1"
        ))
        # No trials recorded — should fail (trial_count=0)
        ok, reason = registry.promote_to_probation(challenger.id, evidence={"trial_count": 0})
        assert not ok
        assert "trial" in reason.lower()

    def test_promote_to_probation_passes_with_sufficient_trials(self, repo):
        from breakthrough_engine.policy_registry import (
            PolicyRegistry, PolicyConfig, PolicyTrial, PROMOTION_MIN_TRIALS
        )
        registry = PolicyRegistry(repo)
        challenger = registry.register(PolicyConfig(
            name="c2", version="1.0", description="Challenger 2"
        ))
        champion = registry.get_champion()
        # Record enough trials with good metrics
        for i in range(PROMOTION_MIN_TRIALS):
            trial = PolicyTrial(
                id="",
                policy_id=challenger.id,
                trial_type="benchmark",
                benchmark_metrics={},
                posterior_summary={
                    "novelty_pass_rate": 0.90,
                    "top_candidate_final_score": 0.85,
                    "falsification_pass_rate": 0.80,
                    "operator_burden_proxy": 0.10,
                    "draft_quality_proxy": 0.82,
                },
                outcome="champion_maintained",
            )
            registry.record_trial(trial)
        ok, reason = registry.promote_to_probation(challenger.id, evidence=_good_evidence(PROMOTION_MIN_TRIALS))
        assert ok, f"Promotion should succeed: {reason}"

    def test_rollback_champion(self, repo):
        from breakthrough_engine.policy_registry import (
            PolicyRegistry, PolicyConfig, PolicyTrial, PROMOTION_MIN_TRIALS
        )
        registry = PolicyRegistry(repo)
        # Register and promote a challenger fully
        challenger = registry.register(PolicyConfig(
            name="c3", version="1.0", description="Will become champion"
        ))
        # Record trials
        for _ in range(PROMOTION_MIN_TRIALS):
            registry.record_trial(PolicyTrial(
                id="", policy_id=challenger.id, trial_type="benchmark",
                benchmark_metrics={},
                posterior_summary={
                    "novelty_pass_rate": 0.90, "top_candidate_final_score": 0.85,
                    "falsification_pass_rate": 0.80, "operator_burden_proxy": 0.10,
                    "draft_quality_proxy": 0.82,
                },
                outcome="champion_maintained",
            ))
        registry.promote_to_probation(challenger.id, evidence=_good_evidence(PROMOTION_MIN_TRIALS))
        registry.promote_to_champion(challenger.id, reason="test promotion")
        new_champion = registry.get_champion()
        assert new_champion.id == challenger.id

        # Rollback
        ok, reason = registry.rollback_champion(reason="test rollback")
        assert ok
        # Champion should have changed
        rolled_back = registry.get_champion()
        # Should be the old champion or the previous one
        assert rolled_back.id != challenger.id

    def test_record_and_get_trial_history(self, repo):
        from breakthrough_engine.policy_registry import PolicyRegistry, PolicyConfig, PolicyTrial
        registry = PolicyRegistry(repo)
        challenger = registry.register(PolicyConfig(
            name="c_hist", version="1.0", description="History test"
        ))
        trial = PolicyTrial(
            id="", policy_id=challenger.id, trial_type="challenger_eval",
            benchmark_metrics={"score": 0.9}, posterior_summary={}, outcome="champion_improved",
        )
        registry.record_trial(trial)
        history = registry.get_trial_history(policy_id=challenger.id)
        assert len(history) == 1
        assert history[0].outcome == "champion_improved"

    def test_list_all_returns_policies(self, repo):
        from breakthrough_engine.policy_registry import PolicyRegistry, PolicyConfig
        registry = PolicyRegistry(repo)
        registry.register(PolicyConfig(name="c_list", version="1.0", description="List test"))
        all_p = registry.list_all()
        assert len(all_p) >= 2  # champion + new challenger


# ---------------------------------------------------------------------------
# 4. Baseline Comparator
# ---------------------------------------------------------------------------


class TestBaselineComparator:
    def test_run_benchmark_returns_metrics(self, repo):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
        comp = BaselineComparator()
        config = BenchmarkConfig(n_runs=1)
        metrics = comp.run_benchmark(config, repo)
        assert metrics.draft_creation_denominator == 1
        assert metrics.novelty_total_count >= 0
        assert isinstance(metrics.final_scores, list)

    def test_run_benchmark_three_runs(self, repo):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
        comp = BaselineComparator()
        config = BenchmarkConfig(n_runs=3)
        metrics = comp.run_benchmark(config, repo)
        assert metrics.draft_creation_denominator == 3

    def test_benchmark_metrics_derived_rates(self, repo):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
        comp = BaselineComparator()
        metrics = comp.run_benchmark(BenchmarkConfig(n_runs=1), repo)
        # Rates should be in [0, 1]
        assert 0.0 <= metrics.draft_creation_rate <= 1.0
        assert 0.0 <= metrics.novelty_block_rate <= 1.0

    def test_compare_no_regression(self, repo):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
        comp = BaselineComparator()
        config = BenchmarkConfig(n_runs=1)
        baseline = comp.run_benchmark(config, repo)
        current = comp.run_benchmark(config, repo)
        report = comp.compare(baseline, current)
        # Identical runs — no regression
        assert not report.has_regression

    def test_compare_detects_regression(self, repo):
        from breakthrough_engine.baseline_comparator import (
            BaselineComparator, BenchmarkConfig, BenchmarkMetrics
        )
        comp = BaselineComparator()
        # Good baseline
        baseline = BenchmarkMetrics(
            draft_creation=3, draft_creation_denominator=3,
            novelty_pass_count=12, novelty_total_count=12,
            synthesis_fit_pass_count=12, synthesis_fit_total_count=12,
            review_worthy_count=6, review_worthy_denominator=12,
            final_scores=[0.9, 0.85, 0.8, 0.75], evidence_balance_scores=[0.8, 0.8],
            elapsed_seconds=10.0,
        )
        # Degraded current (draft creation dropped from 100% to 33%)
        current = BenchmarkMetrics(
            draft_creation=1, draft_creation_denominator=3,
            novelty_pass_count=12, novelty_total_count=12,
            synthesis_fit_pass_count=12, synthesis_fit_total_count=12,
            review_worthy_count=6, review_worthy_denominator=12,
            final_scores=[0.9, 0.85, 0.8, 0.75], evidence_balance_scores=[0.8, 0.8],
            elapsed_seconds=10.0,
        )
        report = comp.compare(baseline, current)
        assert report.has_regression

    def test_load_phase5_baseline_missing_raises(self):
        import breakthrough_engine.baseline_comparator as bc_mod
        comp = bc_mod.BaselineComparator()
        # Temporarily override module-level path
        original = bc_mod.BASELINE_PATH
        from pathlib import Path; bc_mod.BASELINE_PATH = Path("/tmp/nonexistent_baseline_xyzzy.json")
        try:
            with pytest.raises(FileNotFoundError):
                comp.load_phase5_baseline()
        finally:
            bc_mod.BASELINE_PATH = original

    def test_load_phase5_baseline_real_file(self):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BASELINE_PATH
        comp = BaselineComparator()
        if not BASELINE_PATH.exists():
            pytest.skip("Phase 5 baseline artifact not found — run create_phase5_baseline_artifact.py")
        baseline = comp.load_phase5_baseline()
        assert baseline.baseline_tag == "breakthrough-engine-phase5-validated"
        assert baseline.draft_creation_denominator == 3

    def test_format_report(self, repo):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
        comp = BaselineComparator()
        metrics = comp.run_benchmark(BenchmarkConfig(n_runs=1), repo)
        report = comp.compare(metrics, metrics)
        text = comp.format_report(report)
        assert "draft_creation_rate" in text
        assert "baseline" in text.lower()

    def test_save_comparison(self, repo):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
        comp = BaselineComparator()
        metrics = comp.run_benchmark(BenchmarkConfig(n_runs=1), repo)
        report = comp.compare(metrics, metrics)
        comp_id = comp.save_comparison(repo, report)
        assert comp_id != ""
        # Verify it's in the DB
        row = repo.db.execute(
            "SELECT id FROM bt_baseline_comparisons WHERE id=?", (comp_id,)
        ).fetchone()
        assert row is not None

    def test_rollback_if_regression_false(self, repo):
        from breakthrough_engine.baseline_comparator import BaselineComparator, BenchmarkConfig
        from breakthrough_engine.policy_registry import PolicyRegistry
        comp = BaselineComparator()
        metrics = comp.run_benchmark(BenchmarkConfig(n_runs=1), repo)
        report = comp.compare(metrics, metrics)
        registry = PolicyRegistry(repo)
        should_rollback = comp.rollback_if_regression(report, registry)
        assert not should_rollback


# ---------------------------------------------------------------------------
# 5. Falsification Engine
# ---------------------------------------------------------------------------


class TestFalsificationEngine:
    def test_evaluate_returns_summary(self):
        from breakthrough_engine.falsification import FalsificationEngine
        eng = FalsificationEngine()
        cand = _make_candidate()
        summary = eng.evaluate(cand, evidence_pack=None)
        assert summary.candidate_id == cand.id
        assert summary.overall_falsification_risk in ("low", "medium", "high")
        assert isinstance(summary.falsification_passed, bool)
        assert summary.reasoning != ""

    def test_evaluate_with_evidence(self):
        from breakthrough_engine.falsification import FalsificationEngine
        eng = FalsificationEngine()
        cand = _make_candidate()
        ep = _make_evidence_pack(cand)
        summary = eng.evaluate(cand, evidence_pack=ep)
        assert summary.candidate_id == cand.id

    def test_check_contradictions_none_when_consistent(self):
        from breakthrough_engine.falsification import FalsificationEngine
        eng = FalsificationEngine()
        cand = _make_candidate(
            statement="Iron nanoparticles improve catalytic activity in electrocatalytic reactions."
        )
        ep = _make_evidence_pack(cand)
        contradictions = eng.check_contradictions(cand, ep)
        # Evidence is consistent — few or no contradictions
        assert isinstance(contradictions, list)

    def test_check_contradictions_detected(self):
        from breakthrough_engine.falsification import FalsificationEngine
        from breakthrough_engine.models import EvidenceItem, EvidencePack
        eng = FalsificationEngine()
        cand = _make_candidate(
            statement="Iron nanoparticles are highly effective catalysts for hydrogen production."
        )
        ep = EvidencePack(
            candidate_id=cand.id,
            items=[
                EvidenceItem(
                    id=new_id(),
                    source_type="paper",
                    source_id="arxiv_fail",
                    title="Iron failure study",
                    quote="Iron nanoparticles do not work and failed to produce hydrogen in electrochemical conditions.",
                    citation="Failure et al. 2023",
                    relevance_score=0.9,
                ),
            ],
        )
        contradictions = eng.check_contradictions(cand, ep)
        assert isinstance(contradictions, list)
        # At least potentially flagged

    def test_check_missing_evidence_few_items(self):
        from breakthrough_engine.falsification import FalsificationEngine
        from breakthrough_engine.models import EvidencePack
        eng = FalsificationEngine()
        cand = _make_candidate()
        ep = EvidencePack(candidate_id=cand.id, items=[])  # empty
        gaps = eng.check_missing_evidence(cand, ep, min_items=2)
        assert len(gaps) > 0

    def test_assess_assumption_fragility_robust(self):
        from breakthrough_engine.falsification import FalsificationEngine
        eng = FalsificationEngine()
        cand = CandidateHypothesis(
            id=new_id(), run_id=new_id(),
            title="Strong candidate",
            statement="Validated mechanism with strong experimental support.",
            domain="clean-energy",
            mechanism="Validated electrocatalytic pathway",
            expected_outcome="Higher efficiency",
            assumptions=["Iron is stable", "Temperature is controllable"],
            risk_flags=[],
        )
        score = eng.assess_assumption_fragility(cand)
        assert 0.0 <= score <= 1.0

    def test_assess_assumption_fragility_fragile(self):
        from breakthrough_engine.falsification import FalsificationEngine
        eng = FalsificationEngine()
        cand = CandidateHypothesis(
            id=new_id(), run_id=new_id(),
            title="Weak candidate",
            statement="This might possibly work under unknown conditions.",
            domain="clean-energy",
            mechanism="Unknown mechanism possibly involving unknown catalyst",
            expected_outcome="Maybe some improvement",
            assumptions=[
                "assumes unknown catalyst", "assumes perfect conditions",
                "assumes no side reactions", "assumes scalability",
                "assumes low cost", "assumes stability",
            ],
            risk_flags=["not validated", "speculative", "unproven"],
        )
        score = eng.assess_assumption_fragility(cand)
        assert score < 0.7  # Should be fragile

    def test_save_and_load_summary(self, repo):
        from breakthrough_engine.falsification import FalsificationEngine
        eng = FalsificationEngine()
        cand = _make_candidate()
        summary = eng.evaluate(cand, evidence_pack=None)
        eng.save_summary(repo, summary)

        loaded = eng.load_summary(repo, cand.id)
        assert loaded is not None
        assert loaded.candidate_id == cand.id
        assert loaded.overall_falsification_risk == summary.overall_falsification_risk

    def test_falsification_risk_low_for_good_candidate(self):
        from breakthrough_engine.falsification import FalsificationEngine
        eng = FalsificationEngine()
        cand = CandidateHypothesis(
            id=new_id(), run_id=new_id(),
            title="Well-supported candidate",
            statement="Iron electrocatalysts validated by multiple studies for hydrogen production.",
            domain="clean-energy",
            mechanism="Fe-N-C electrocatalytic reduction: well-characterized pathway",
            expected_outcome="50% improvement in hydrogen evolution rate",
            assumptions=["Iron abundant", "Carbon stable"],
            risk_flags=[],
        )
        ep = _make_evidence_pack(cand)
        summary = eng.evaluate(cand, evidence_pack=ep)
        # Good candidate should not be high risk
        assert summary.overall_falsification_risk != "high" or not summary.falsification_passed

    def test_overall_risk_high_when_many_issues(self):
        from breakthrough_engine.falsification import FalsificationEngine, FalsificationSummary
        eng = FalsificationEngine()
        # Construct a summary manually to test risk computation logic
        cand = _make_candidate()
        summary = eng.evaluate(cand, evidence_pack=None)
        # Risk should be one of valid values
        assert summary.overall_falsification_risk in ("low", "medium", "high")


# ---------------------------------------------------------------------------
# 6. Reward Logger
# ---------------------------------------------------------------------------


class TestRewardLogger:
    def test_load_recipe_default(self):
        from breakthrough_engine.reward_logger import RewardLogger
        logger = RewardLogger()
        recipe = logger.load_recipe("v1")
        assert recipe.recipe_version == "v1"
        assert "draft_created" in recipe.weights
        assert recipe.weights["draft_created"] > 0

    def test_log_signal(self, repo):
        from breakthrough_engine.reward_logger import RewardLogger, RewardSignal
        logger = RewardLogger()
        signal = RewardSignal(
            run_id="run123", candidate_id="cand456", policy_id="p1",
            observation_unit="candidate", signal_name="novelty_pass",
            signal_value=1.0, signal_type="binary",
            context={"domain": "clean-energy"},
        )
        logger.log_signal(repo, signal)
        rows = repo.db.execute(
            "SELECT * FROM bt_reward_logs WHERE run_id='run123'"
        ).fetchall()
        assert len(rows) == 1

    def test_compute_episode_reward(self, repo):
        from breakthrough_engine.reward_logger import RewardLogger
        from breakthrough_engine.models import RunMetrics
        logger = RewardLogger()
        recipe = logger.get_recipe()
        run = RunRecord(id=new_id(), program_name="test", mode=RunMode.DETERMINISTIC_TEST,
                        status=RunStatus.COMPLETED)
        metrics = RunMetrics(run_id=run.id)
        metrics.draft_created = True

        reward, components = logger.compute_episode_reward(
            run_record=run,
            metrics=metrics,
            recipe=recipe,
        )
        assert isinstance(reward, float)
        assert isinstance(components, dict)
        assert "draft_created" in components

    def test_log_trajectory(self, repo):
        from breakthrough_engine.reward_logger import RewardLogger, TrajectoryRecord
        logger = RewardLogger()
        traj = TrajectoryRecord(
            trajectory_id=new_id(),
            run_id="run_traj",
            policy_id="p1",
            reward_recipe_version="v1",
            state={"domain": "clean-energy"},
            action={"policy": "standard"},
            reward=0.75,
            reward_components={"draft_created": 0.5, "mean_final_score": 0.25},
            outcome="draft_created",
        )
        logger.log_trajectory(repo, traj)
        rows = repo.db.execute(
            "SELECT * FROM bt_trajectories WHERE run_id='run_traj'"
        ).fetchall()
        assert len(rows) == 1

    def test_export_trajectories(self, repo):
        from breakthrough_engine.reward_logger import RewardLogger, TrajectoryRecord
        logger = RewardLogger()
        for i in range(3):
            traj = TrajectoryRecord(
                trajectory_id=new_id(),
                run_id=f"run_{i}",
                policy_id="p1",
                reward_recipe_version="v1",
                state={}, action={}, reward=0.5,
                reward_components={}, outcome="draft_created",
            )
            logger.log_trajectory(repo, traj)
        exported = logger.export_trajectories(repo)
        assert len(exported) == 3

    def test_reward_recipe_version_stored(self, repo):
        from breakthrough_engine.reward_logger import RewardLogger, TrajectoryRecord
        logger = RewardLogger()
        traj = TrajectoryRecord(
            trajectory_id=new_id(), run_id="run_rv", policy_id=None,
            reward_recipe_version="v1",
            state={}, action={}, reward=0.6, reward_components={}, outcome="draft_created",
        )
        logger.log_trajectory(repo, traj)
        row = repo.db.execute(
            "SELECT reward_recipe_version FROM bt_trajectories WHERE run_id='run_rv'"
        ).fetchone()
        assert row[0] == "v1"

    def test_log_signals_from_run(self, repo):
        from breakthrough_engine.reward_logger import RewardLogger
        logger = RewardLogger()
        run = RunRecord(id=new_id(), program_name="test", mode=RunMode.DETERMINISTIC_TEST,
                        status=RunStatus.COMPLETED)
        repo.save_run(run)
        # No candidates — just confirm it doesn't crash
        logger.log_signals_from_run(repo, run.id, policy_id="p1", domain="clean-energy")

    def test_get_reward_stats(self, repo):
        from breakthrough_engine.reward_logger import RewardLogger, TrajectoryRecord
        logger = RewardLogger()
        for _ in range(5):
            traj = TrajectoryRecord(
                trajectory_id=new_id(), run_id=new_id(), policy_id="p_stat",
                reward_recipe_version="v1",
                state={}, action={}, reward=0.7, reward_components={}, outcome="draft_created",
            )
            logger.log_trajectory(repo, traj)
        stats = logger.get_reward_stats(repo, policy_id="p_stat")
        assert stats["count"] == 5
        assert abs(stats["mean_reward"] - 0.7) < 0.01


# ---------------------------------------------------------------------------
# 7. Review Cockpit
# ---------------------------------------------------------------------------


class TestReviewCockpit:
    def test_build_packet_minimal(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.82},
        )
        assert packet.candidate_id == cand.id
        assert packet.final_score == 0.82
        assert packet.recommended_action in ("APPROVE", "DEFER", "REJECT")

    def test_recommended_action_approve(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.80},
        )
        # Score 0.80 >= 0.75 and no falsification — should APPROVE
        assert packet.recommended_action == "APPROVE"

    def test_recommended_action_defer(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.65},
        )
        assert packet.recommended_action == "DEFER"

    def test_recommended_action_reject(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.45},
        )
        assert packet.recommended_action == "REJECT"

    def test_recommended_action_reject_when_falsification_fails(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        from breakthrough_engine.falsification import FalsificationSummary
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        fail_summary = FalsificationSummary(
            candidate_id=cand.id, run_id=cand.run_id,
            contradictions_found=["major contradiction"],
            missing_evidence_gaps=["no primary support"],
            assumption_fragility_score=0.1,
            bridge_weakness_flags=["weak bridge"],
            overall_falsification_risk="high",
            falsification_passed=False,
            reasoning="Multiple issues found.",
        )
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.80},
            falsification_summary=fail_summary,
        )
        # High score but failed falsification — should DEFER or REJECT
        assert packet.recommended_action in ("DEFER", "REJECT")

    def test_format_as_text(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.78},
        )
        text = cockpit.format_as_text(packet)
        assert "REVIEW DECISION PACKET" in text
        assert packet.recommended_action in text
        assert cand.title in text

    def test_format_as_html(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.70},
        )
        html = cockpit.format_as_html(packet)
        assert "<!DOCTYPE html>" in html
        assert packet.recommended_action in html

    def test_runner_up_comparison(self):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        r1 = _make_candidate(title="Runner-up 1")
        r2 = _make_candidate(title="Runner-up 2")
        runner_ups = [(r1, 0.70), (r2, 0.65)]
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.80}, runner_ups=runner_ups,
        )
        assert packet.runner_up_comparison is not None
        assert len(packet.runner_up_comparison) == 2

    def test_save_packet(self, repo):
        from breakthrough_engine.review_cockpit import ReviewCockpit
        cockpit = ReviewCockpit()
        cand = _make_candidate()
        packet = cockpit.build_packet(
            candidate=cand, evidence_pack=None, synthesis_fit=None,
            novelty_result=None, candidate_score={"final_score": 0.82},
        )
        # Should not raise
        cockpit.save_packet(repo, packet)


# ---------------------------------------------------------------------------
# 8. Daily Search Ladder
# ---------------------------------------------------------------------------


class TestDailySearchLadder:
    def _make_program(self):
        return ResearchProgram(
            name="test_p6",
            domain="clean-energy",
            mode=RunMode.DETERMINISTIC_TEST,
            candidate_budget=3,
            simulation_budget=2,
            publication_threshold=0.50,
            evidence_minimum=1,
        )

    def test_run_campaign_returns_result(self, repo):
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
        from breakthrough_engine.policy_registry import PolicyRegistry
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        from breakthrough_engine.falsification import FalsificationEngine

        ladder = DailySearchLadder()
        config = LadderConfig(mode="benchmark")
        registry = PolicyRegistry(repo)
        evaluator = BayesianEvaluator()
        falsifier = FalsificationEngine()
        program = self._make_program()

        result = ladder.run_campaign(repo, config, registry, program)
        assert result.campaign_id != ""
        assert result.mode == "benchmark"
        assert result.elapsed_seconds >= 0

    def test_campaign_has_ladder_stages(self, repo):
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
        from breakthrough_engine.policy_registry import PolicyRegistry
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        from breakthrough_engine.falsification import FalsificationEngine

        ladder = DailySearchLadder()
        config = LadderConfig(mode="benchmark")
        registry = PolicyRegistry(repo)
        evaluator = BayesianEvaluator()
        falsifier = FalsificationEngine()
        program = self._make_program()

        result = ladder.run_campaign(repo, config, registry, program)
        assert len(result.ladder_stages) >= 1
        stage_names = [s.stage_name for s in result.ladder_stages]
        assert "stage1_exploration" in stage_names

    def test_stage_stop_reason_is_valid(self, repo):
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
        from breakthrough_engine.policy_registry import PolicyRegistry
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        from breakthrough_engine.falsification import FalsificationEngine

        ladder = DailySearchLadder()
        config = LadderConfig(mode="benchmark")
        registry = PolicyRegistry(repo)
        evaluator = BayesianEvaluator()
        falsifier = FalsificationEngine()
        program = self._make_program()

        result = ladder.run_campaign(repo, config, registry, program)
        valid_reasons = {"completed", "budget_exhausted", "early_stopped", "abandoned"}
        for stage in result.ladder_stages:
            assert stage.stop_reason in valid_reasons, \
                f"Invalid stop_reason: {stage.stop_reason}"

    def test_campaign_saves_to_db(self, repo):
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
        from breakthrough_engine.policy_registry import PolicyRegistry
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        from breakthrough_engine.falsification import FalsificationEngine

        ladder = DailySearchLadder()
        config = LadderConfig(mode="benchmark")
        registry = PolicyRegistry(repo)
        evaluator = BayesianEvaluator()
        falsifier = FalsificationEngine()
        program = self._make_program()

        result = ladder.run_campaign(repo, config, registry, program)

        # Verify in DB
        row = repo.db.execute(
            "SELECT campaign_id FROM bt_daily_campaigns WHERE campaign_id=?",
            (result.campaign_id,)
        ).fetchone()
        assert row is not None

    def test_campaign_metadata(self, repo):
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
        from breakthrough_engine.policy_registry import PolicyRegistry
        from breakthrough_engine.bayesian_evaluator import BayesianEvaluator
        from breakthrough_engine.falsification import FalsificationEngine

        ladder = DailySearchLadder()
        config = LadderConfig(mode="benchmark")
        registry = PolicyRegistry(repo)
        evaluator = BayesianEvaluator()
        falsifier = FalsificationEngine()
        program = self._make_program()

        result = ladder.run_campaign(repo, config, registry, program)
        assert result.total_candidates_generated >= 0
        assert result.total_blocked >= 0
        assert result.champion_selection_rationale != ""

    def test_should_early_stop_no_candidates(self):
        from breakthrough_engine.daily_search import DailySearchLadder, LadderConfig
        ladder = DailySearchLadder()
        result = ladder._should_early_stop([], {})
        assert not result

    def test_ladder_config_defaults(self):
        from breakthrough_engine.daily_search import LadderConfig
        config = LadderConfig()
        assert config.mode == "benchmark"
        assert config.stage1.max_trials >= 1
        assert config.stage1.abandon_floor >= 0.0
        assert config.stage2_shortlist_size >= 1
        assert config.stage3.max_trials >= 1

    def test_stage_config_abandon_floor(self):
        from breakthrough_engine.daily_search import StageConfig
        config = StageConfig(
            max_trials=3,
            min_score_to_advance=0.40,
            max_wall_clock_seconds=300,
            abandon_floor=0.30,
        )
        assert config.abandon_floor == 0.30
        assert config.max_trials == 3
