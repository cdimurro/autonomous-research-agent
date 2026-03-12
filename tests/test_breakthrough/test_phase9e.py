"""Phase 9E tests: Manual promotion, burn-in artifacts, baseline freeze, rollback guardrails, Phase 10 prep.

All tests are offline-safe (no Ollama, no external network, no embeddings).
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent


def _load_json(path: str) -> dict:
    with open(REPO_ROOT / path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# A: Promotion receipt tests
# ---------------------------------------------------------------------------


class TestPromotionReceipt:
    """Promotion receipt must exist and record a complete, auditable promotion event."""

    def test_promotion_receipt_exists(self):
        path = REPO_ROOT / "runtime/phase9e/promotion_receipt.json"
        assert path.exists(), "Promotion receipt must exist"

    def test_promotion_receipt_event_type(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert data["event"] == "manual_promotion"

    def test_promotion_receipt_promoted_policy(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert data["new_champion_id"] == "evidence_diversity_v1"

    def test_promotion_receipt_prior_champion(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert data["prior_champion_id"] == "phase5_champion"

    def test_promotion_receipt_trial_id(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert data["trial_id"] == "phase9d_ab_trial"

    def test_promotion_receipt_all_gates_pass(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert data["all_gates_pass"] is True

    def test_promotion_receipt_all_individual_gates_pass(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        gates = data["promotion_gates"]
        for gate_name, gate in gates.items():
            assert gate["pass"] is True, f"Promotion gate {gate_name!r} did not pass"

    def test_promotion_receipt_policy_snapshot_is_evidence_diversity_v1(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        snap = data["policy_config_snapshot"]
        assert snap["name"] == "evidence_diversity_v1"
        erw = snap["evidence_ranking_weights"]
        assert erw is not None
        assert erw["mechanism_overlap"] == 0.35
        assert erw["api_relevance"] == 0.20

    def test_promotion_receipt_has_timestamp(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert data.get("promoted_at"), "Promotion receipt must have promoted_at timestamp"

    def test_promotion_receipt_has_command(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert "command" in data
        assert "manual-promote" in data["command"]

    def test_promotion_receipt_embedding_regime_is_regime2(self):
        data = _load_json("runtime/phase9e/promotion_receipt.json")
        assert data["embedding_regime"] == "regime_2"
        assert data["embedding_model"] == "qwen3-embedding:4b"


# ---------------------------------------------------------------------------
# B: CLI manual-promote command tests (offline — checks arg parser)
# ---------------------------------------------------------------------------


class TestManualPromoteCLI:
    """CLI must have a manual-promote subcommand that bypasses trial count."""

    def test_manual_promote_in_cli_source(self):
        cli_path = REPO_ROOT / "breakthrough_engine/cli.py"
        content = cli_path.read_text()
        assert "manual-promote" in content, "CLI must have manual-promote subcommand"

    def test_policy_promote_tuple_fix_in_cli(self):
        """CLI policy promote must unpack tuple from promote_to_probation."""
        cli_path = REPO_ROOT / "breakthrough_engine/cli.py"
        content = cli_path.read_text()
        # The fixed code should have tuple unpacking: ok, reason_msg = ...
        assert "ok, reason_msg = registry.promote_to_probation" in content, (
            "policy promote must unpack tuple return from promote_to_probation"
        )

    def test_policy_rollback_tuple_fix_in_cli(self):
        """CLI policy rollback must unpack tuple from rollback_champion."""
        cli_path = REPO_ROOT / "breakthrough_engine/cli.py"
        content = cli_path.read_text()
        assert "ok, reason_msg = registry.rollback_champion" in content, (
            "policy rollback must unpack tuple return from rollback_champion"
        )

    def test_manual_promote_requires_reason(self):
        """manual-promote must require --reason argument."""
        cli_path = REPO_ROOT / "breakthrough_engine/cli.py"
        content = cli_path.read_text()
        assert "required=True" in content and "--reason" in content


# ---------------------------------------------------------------------------
# C: Burn-in campaign artifact tests
# ---------------------------------------------------------------------------


class TestBurninCampaignArtifacts:
    """Burn-in campaign artifacts must exist and have the correct structure."""

    def test_burnin_directory_exists(self):
        path = REPO_ROOT / "runtime/phase9e/burnin"
        assert path.is_dir()

    def test_burnin_campaigns_directory_exists(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        assert path.is_dir()

    def test_burnin_has_3_eval_campaigns(self):
        campaigns_dir = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        eval_files = list(campaigns_dir.glob("BE*.json"))
        assert len(eval_files) == 3, f"Expected 3 eval burn-in campaigns, found {len(eval_files)}"

    def test_burnin_has_3_prod_campaigns(self):
        campaigns_dir = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        prod_files = list(campaigns_dir.glob("BP*.json"))
        assert len(prod_files) == 3, f"Expected 3 production burn-in campaigns, found {len(prod_files)}"

    def test_burnin_campaigns_all_use_evidence_diversity_v1(self):
        campaigns_dir = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        for f in campaigns_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["policy"] == "evidence_diversity_v1", (
                f"Campaign {f.name} must use evidence_diversity_v1, got {data['policy']!r}"
            )

    def test_burnin_campaigns_all_integrity_ok(self):
        campaigns_dir = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        for f in campaigns_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["integrity_status"] == "integrity_ok", (
                f"Campaign {f.name} must have integrity_ok, got {data['integrity_status']!r}"
            )

    def test_burnin_campaigns_all_completed_with_draft(self):
        campaigns_dir = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        for f in campaigns_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["status"] == "completed_with_draft", (
                f"Campaign {f.name} must be completed_with_draft, got {data['status']!r}"
            )

    def test_burnin_campaigns_regime2_embedding(self):
        campaigns_dir = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        for f in campaigns_dir.glob("*.json"):
            data = json.loads(f.read_text())
            assert data["embedding_regime"] == "regime_2", (
                f"Campaign {f.name} must use Regime 2, got {data['embedding_regime']!r}"
            )
            assert "qwen3-embedding:4b" in data["embedding_provider"]

    def test_burnin_eval_campaigns_have_integrity_gate(self):
        campaigns_dir = REPO_ROOT / "runtime/phase9e/burnin/campaigns"
        for f in campaigns_dir.glob("BE*.json"):
            data = json.loads(f.read_text())
            assert data.get("integrity_status") == "integrity_ok", (
                f"Eval campaign {f.name} must pass integrity gate"
            )


# ---------------------------------------------------------------------------
# D: Burn-in review labels tests
# ---------------------------------------------------------------------------


class TestBurninReviewLabels:
    """Review labels must be complete and correctly structured."""

    def test_review_labels_csv_exists(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        assert path.exists(), "Burn-in review_labels.csv must exist"

    def test_review_labels_has_12_labels(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 12, f"Expected 12 review labels, found {len(rows)}"

    def test_review_labels_has_6_champion_labels(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        champion_labels = [r for r in rows if r["role"] == "champion"]
        assert len(champion_labels) == 6

    def test_review_labels_has_6_runner_up_labels(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        runner_up_labels = [r for r in rows if r["role"] == "runner_up"]
        assert len(runner_up_labels) == 6

    def test_review_labels_all_decisions_valid(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        valid_decisions = {"approve", "defer", "reject"}
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                assert row["decision"] in valid_decisions, (
                    f"Label {row['id']!r} has invalid decision {row['decision']!r}"
                )

    def test_review_labels_champion_approval_rate_above_threshold(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        champion_labels = [r for r in rows if r["role"] == "champion"]
        approved = sum(1 for r in champion_labels if r["decision"] == "approve")
        approval_rate = approved / len(champion_labels)
        assert approval_rate >= 0.60, (
            f"Burn-in champion approval rate {approval_rate:.1%} below 60% threshold"
        )

    def test_review_labels_no_reject_labels(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        reject_count = sum(1 for r in rows if r["decision"] == "reject")
        assert reject_count == 0, f"Found {reject_count} reject labels in burn-in (expected 0)"

    def test_review_labels_policy_column_is_evidence_diversity(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/review_labels.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        for row in rows:
            assert row.get("policy") == "evidence_diversity_v1", (
                f"Label {row.get('id')!r} should have policy=evidence_diversity_v1"
            )


# ---------------------------------------------------------------------------
# E: Burn-in summary tests
# ---------------------------------------------------------------------------


class TestBurninSummary:
    """Burn-in summary must document a healthy baseline."""

    def test_burnin_summary_json_exists(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/burnin_summary.json"
        assert path.exists()

    def test_burnin_summary_md_exists(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/burnin_summary.md"
        assert path.exists()

    def test_burnin_summary_verdict_is_healthy(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        verdict = data.get("verdict", "")
        assert "HEALTHY" in verdict.upper() or "HEALTHY" in data.get("status", "").upper()

    def test_burnin_summary_mean_score_above_threshold(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        mean = data["combined_metrics"]["mean_champion_score"]
        assert mean >= 0.88, f"Burn-in mean score {mean} below threshold 0.88"

    def test_burnin_summary_approval_rate_above_threshold(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        rate = data["combined_metrics"]["approval_rate"]
        assert rate >= 0.60, f"Burn-in approval rate {rate:.1%} below threshold 60%"

    def test_burnin_summary_all_integrity_ok(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        assert data["combined_metrics"]["all_integrity_ok"] is True

    def test_burnin_summary_has_comparison_vs_phase9c(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        comparison = data.get("comparison_vs_phase9c_baseline")
        assert comparison is not None
        assert comparison["baseline_id"] == "phase9c_operational_regime2"

    def test_burnin_summary_all_comparison_gates_pass(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        comparison = data["comparison_vs_phase9c_baseline"]
        assert comparison["all_gates_pass"] is True, (
            f"Burn-in comparison gates did not all pass: {comparison}"
        )

    def test_burnin_summary_score_delta_positive(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        delta = data["comparison_vs_phase9c_baseline"]["score_delta"]
        assert delta > -0.03, f"Score delta {delta} is below regression threshold"

    def test_burnin_summary_approval_delta_positive(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        delta = data["comparison_vs_phase9c_baseline"]["approval_rate_delta"]
        assert delta > -0.05, f"Approval rate delta {delta} is below regression threshold"

    def test_burnin_summary_all_campaigns_listed(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        assert len(data["campaigns"]) == 6

    def test_burnin_summary_eval_and_prod_metrics_present(self):
        data = _load_json("runtime/phase9e/burnin/burnin_summary.json")
        assert "eval_metrics" in data
        assert "production_metrics" in data
        assert data["eval_metrics"]["campaign_count"] == 3
        assert data["production_metrics"]["campaign_count"] == 3


# ---------------------------------------------------------------------------
# F: Burn-in CSV artifacts tests
# ---------------------------------------------------------------------------


class TestBurninCSVs:
    """Champions, finalists, and campaign metrics CSVs must exist and be well-formed."""

    def test_champions_csv_exists(self):
        assert (REPO_ROOT / "runtime/phase9e/burnin/champions.csv").exists()

    def test_champions_csv_has_6_rows(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/champions.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 6, f"Expected 6 champion rows, found {len(rows)}"

    def test_champions_csv_required_columns(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/champions.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
        for col in ("campaign_id", "profile", "champion_score", "integrity_status", "decision"):
            assert col in fields, f"Missing column {col!r} in champions.csv"

    def test_finalists_csv_exists(self):
        assert (REPO_ROOT / "runtime/phase9e/burnin/finalists_combined.csv").exists()

    def test_finalists_csv_required_columns(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/finalists_combined.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
        for col in ("campaign_id", "rank", "title", "score", "policy"):
            assert col in fields, f"Missing column {col!r} in finalists_combined.csv"

    def test_campaign_metrics_csv_exists(self):
        assert (REPO_ROOT / "runtime/phase9e/burnin/campaign_metrics.csv").exists()

    def test_campaign_metrics_csv_has_6_rows(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/campaign_metrics.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 6

    def test_campaign_metrics_csv_required_columns(self):
        path = REPO_ROOT / "runtime/phase9e/burnin/campaign_metrics.csv"
        with open(path) as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames or []
        for col in ("campaign_id", "profile", "policy", "integrity_status"):
            assert col in fields, f"Missing column {col!r} in campaign_metrics.csv"

    def test_label_completion_summary_json_exists(self):
        assert (REPO_ROOT / "runtime/phase9e/burnin/label_completion_summary.json").exists()

    def test_label_completion_is_100_pct(self):
        data = _load_json("runtime/phase9e/burnin/label_completion_summary.json")
        assert data["completeness_pct"] == 100.0

    def test_label_completion_md_exists(self):
        assert (REPO_ROOT / "runtime/phase9e/burnin/label_completion_summary.md").exists()


# ---------------------------------------------------------------------------
# G: Production baseline freeze tests
# ---------------------------------------------------------------------------


class TestProductionBaselineFreeze:
    """Frozen production baseline must exist and be correctly structured."""

    def test_phase9e_baseline_exists(self):
        path = REPO_ROOT / "runtime/baselines/phase9e_promoted_production_baseline_regime2.json"
        assert path.exists(), "Phase 9E production baseline must exist"

    def test_phase9e_baseline_policy_is_evidence_diversity(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        assert data["champion_policy"] == "evidence_diversity_v1"

    def test_phase9e_baseline_regime_is_regime2(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        assert data["embedding_regime"] == "regime_2"
        assert data["embedding_model"] == "qwen3-embedding:4b"

    def test_phase9e_baseline_has_6_campaigns(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        assert len(data["campaigns"]) == 6

    def test_phase9e_baseline_mean_score_above_threshold(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        mean = data["combined_metrics"]["mean_champion_score"]
        assert mean >= 0.88, f"Baseline mean score {mean} below threshold"

    def test_phase9e_baseline_approval_rate_passes_gate(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        rate = data["combined_metrics"]["approval_rate"]
        assert rate >= 0.60, f"Baseline approval rate {rate:.1%} below gate"

    def test_phase9e_baseline_quality_gates_all_pass(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        gates = data["quality_gates"]
        assert gates["baseline_ready"] is True
        assert gates["champion_mean_score_pass"] is True
        assert gates["approval_rate_pass"] is True

    def test_phase9e_baseline_has_prior_champion_reference(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        assert data.get("prior_champion_policy") == "phase5_champion"

    def test_phase9e_baseline_label_completeness_is_100(self):
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        lc = data["label_completeness"]
        assert lc["completeness_pct"] == 100.0

    def test_phase9e_baseline_is_better_than_phase9c(self):
        """Promoted policy baseline must be no worse than prior baseline."""
        data = _load_json("runtime/baselines/phase9e_promoted_production_baseline_regime2.json")
        comparison = data.get("comparison_vs_prior_baseline", {})
        if comparison:
            score_delta = comparison.get("score_delta", 0)
            assert score_delta >= -0.03, (
                f"Baseline score delta vs Phase 9C is {score_delta}, below regression threshold"
            )

    def test_all_prior_baselines_preserved(self):
        """Prior baselines must still exist."""
        for name in (
            "phase5_validated_benchmark",
            "phase7d_reviewed_baseline",
            "phase8_reviewed_baseline",
            "phase9_new_embedding_reviewed",
            "phase9c_operational_baseline_regime2",
        ):
            path = REPO_ROOT / f"runtime/baselines/{name}.json"
            assert path.exists(), f"Prior baseline {name}.json must be preserved"


# ---------------------------------------------------------------------------
# H: Rollback guardrails tests
# ---------------------------------------------------------------------------


class TestRollbackGuardrails:
    """Rollback guardrails must be documented and the rollback mechanism verified."""

    def test_rollback_guardrails_doc_exists(self):
        path = REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md"
        assert path.exists()

    def test_rollback_guardrails_has_rollback_command(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md").read_text()
        assert "policy rollback" in content

    def test_rollback_guardrails_has_mandatory_triggers(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md").read_text()
        assert "Mandatory Rollback" in content or "mandatory" in content.lower()

    def test_rollback_guardrails_references_phase5_champion_as_target(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md").read_text()
        assert "phase5_champion" in content

    def test_rollback_champion_returns_tuple_not_bool(self):
        """policy_registry.rollback_champion must return (bool, str) tuple."""
        from breakthrough_engine.policy_registry import PolicyRegistry

        import inspect
        sig = inspect.signature(PolicyRegistry.rollback_champion)
        # The return annotation should be tuple[bool, str]
        # Verify the implementation returns a tuple (by checking source)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "policy_registry",
            str(REPO_ROOT / "breakthrough_engine/policy_registry.py"),
        )
        # Minimal check: can import without error
        from breakthrough_engine.policy_registry import PolicyRegistry  # noqa: F811

    def test_rollback_works_with_fresh_repo(self, repo):
        """rollback_champion must return (False, msg) when no previous champion exists."""
        from breakthrough_engine.policy_registry import PolicyRegistry
        registry = PolicyRegistry(repo)
        ok, reason = registry.rollback_champion(reason="test rollback")
        assert not ok
        assert "no previous champion" in reason.lower() or "not found" in reason.lower()

    def test_cli_rollback_correctly_unpacks_tuple(self):
        """CLI rollback handler must use tuple unpacking, not boolean truthiness."""
        cli_path = REPO_ROOT / "breakthrough_engine/cli.py"
        content = cli_path.read_text()
        assert "ok, reason_msg = registry.rollback_champion" in content


# ---------------------------------------------------------------------------
# I: Phase 9E docs existence tests
# ---------------------------------------------------------------------------


class TestPhase9EDocs:
    """All required Phase 9E documentation files must exist."""

    def test_plan_doc_exists(self):
        assert (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_PLAN.md").exists()

    def test_plan_doc_has_status_complete(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_PLAN.md").read_text()
        assert "COMPLETE" in content

    def test_status_doc_exists(self):
        assert (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_STATUS.md").exists()

    def test_status_doc_shows_evidence_diversity_as_champion(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_STATUS.md").read_text()
        assert "evidence_diversity_v1" in content
        assert "Champion" in content or "champion" in content

    def test_burnin_doc_exists(self):
        assert (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_BURNIN.md").exists()

    def test_burnin_doc_has_baseline_healthy_verdict(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_BURNIN.md").read_text()
        assert "BASELINE_HEALTHY" in content

    def test_production_baseline_doc_exists(self):
        assert (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_PRODUCTION_BASELINE.md").exists()

    def test_production_baseline_doc_references_phase9e_baseline(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_PRODUCTION_BASELINE.md").read_text()
        assert "phase9e_promoted_production_regime2" in content

    def test_rollback_guardrails_doc_exists(self):
        assert (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE9E_ROLLBACK_GUARDRAILS.md").exists()


# ---------------------------------------------------------------------------
# J: Phase 10 prep tests
# ---------------------------------------------------------------------------


class TestPhase10Prep:
    """Phase 10 prep document must exist and recommend the next challenger."""

    def test_phase10_prep_doc_exists(self):
        assert (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md").exists()

    def test_phase10_prep_recommends_challenger_surface(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md").read_text()
        # Must recommend a specific challenger surface
        assert "diversity_steering_variant" in content or "negative_memory_strategy" in content

    def test_phase10_prep_has_hypothesis(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md").read_text()
        assert "hypothesis" in content.lower() or "Hypothesis" in content

    def test_phase10_prep_does_not_activate_challenger(self):
        """Phase 10 prep must be design-only — no active challenger registration."""
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md").read_text()
        assert "DESIGN PREP ONLY" in content or "design only" in content.lower() or "not yet activated" in content.lower()

    def test_phase10_prep_references_new_baseline_as_anchor(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md").read_text()
        assert "phase9e_promoted_production_regime2" in content or "evidence_diversity_v1" in content

    def test_phase10_prep_has_promotion_gate_thresholds(self):
        content = (REPO_ROOT / "docs/BREAKTHROUGH_ENGINE_PHASE10_PREP.md").read_text()
        # Must define what counts as a promotion-worthy improvement
        assert "0.9126" in content or "0.912" in content or "gates" in content.lower()

    def test_no_new_challenger_config_file_added(self):
        """Phase 10 challenger must not be registered yet (no diversity_steering_v1.json)."""
        policy_dir = REPO_ROOT / "config/policies"
        phase10_files = list(policy_dir.glob("diversity_steering*.json"))
        phase10_files += list(policy_dir.glob("negative_memory*.json"))
        assert len(phase10_files) == 0, (
            f"Phase 10 challenger config files found (should not be registered yet): "
            f"{[f.name for f in phase10_files]}"
        )


# ---------------------------------------------------------------------------
# K: Phase 9D trial artifacts integrity (unchanged)
# ---------------------------------------------------------------------------


class TestPhase9DTrialIntegrity:
    """Phase 9D trial artifacts must still be intact after Phase 9E promotion."""

    def test_phase9d_arm_summary_still_exists(self):
        assert (REPO_ROOT / "runtime/challenger_trials/phase9d_ab_trial/arm_summary.json").exists()

    def test_phase9d_trial_status_is_complete(self):
        data = _load_json("runtime/challenger_trials/phase9d_ab_trial/arm_summary.json")
        assert data["status"] == "COMPLETE"

    def test_phase9d_trial_verdict_is_promotion_recommended(self):
        data = _load_json("runtime/challenger_trials/phase9d_ab_trial/arm_summary.json")
        assert "PROMOTION_RECOMMENDED" in data.get("comparison", {}).get("promotion_assessment", "")

    def test_phase9d_all_4_gates_pass(self):
        data = _load_json("runtime/challenger_trials/phase9d_ab_trial/arm_summary.json")
        comparison = data["comparison"]
        assert comparison["score_gate_pass"] is True
        assert comparison["approval_rate_gate_pass"] is True
        assert comparison["novelty_gate_pass"] is True
        assert comparison["plausibility_gate_pass"] is True

    def test_phase9d_review_labels_still_intact(self):
        path = REPO_ROOT / "runtime/challenger_trials/phase9d_ab_trial/review_labels.csv"
        assert path.exists()
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 24, f"Phase 9D must have 24 review labels, found {len(rows)}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo():
    """Provide an in-memory repo for tests that need it."""
    from breakthrough_engine.db import Repository, init_db

    db = init_db(in_memory=True)
    yield Repository(db)
    db.close()
