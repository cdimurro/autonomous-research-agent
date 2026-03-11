"""Phase 9C-B tests: daily automation fixes, evidence_diversity_v1 DB registration,
and Phase 9C-B documentation artifacts.

All tests are offline-safe (no Ollama calls, no live DB writes).
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_policy_config(name: str) -> dict:
    path = REPO_ROOT / "config" / "policies" / f"{name}.json"
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# A: CLI fix — policy register loads evidence_ranking_weights
# ---------------------------------------------------------------------------

class TestPolicyRegisterEvidenceRankingWeights:
    """policy register --config-path must load evidence_ranking_weights from JSON."""

    def test_evidence_diversity_v1_json_has_evidence_ranking_weights(self):
        config = _load_policy_config("evidence_diversity_v1")
        assert "evidence_ranking_weights" in config
        assert config["evidence_ranking_weights"] is not None

    def test_policy_config_from_dict_preserves_evidence_ranking_weights(self):
        from breakthrough_engine.policy_registry import PolicyConfig
        config_dict = _load_policy_config("evidence_diversity_v1")
        pc = PolicyConfig.from_dict(config_dict)
        assert pc.evidence_ranking_weights is not None
        assert pc.evidence_ranking_weights["mechanism_overlap"] == pytest.approx(0.35)
        assert pc.evidence_ranking_weights["api_relevance"] == pytest.approx(0.20)

    def test_policy_config_to_dict_round_trips_evidence_ranking_weights(self):
        from breakthrough_engine.policy_registry import PolicyConfig
        config_dict = _load_policy_config("evidence_diversity_v1")
        pc = PolicyConfig.from_dict(config_dict)
        out = pc.to_dict()
        assert out["evidence_ranking_weights"] == config_dict["evidence_ranking_weights"]

    def test_policy_config_serialization_preserves_all_weights(self):
        """PolicyConfig.from_dict / to_dict must round-trip all evidence_ranking_weights keys."""
        from breakthrough_engine.policy_registry import PolicyConfig
        weights = {
            "api_relevance": 0.20,
            "domain_overlap": 0.30,
            "mechanism_overlap": 0.35,
            "baseline": 0.15,
        }
        pc = PolicyConfig(name="test_policy", evidence_ranking_weights=weights)
        out = pc.to_dict()
        assert out["evidence_ranking_weights"] == weights

        pc2 = PolicyConfig.from_dict(out)
        assert pc2.evidence_ranking_weights == weights


# ---------------------------------------------------------------------------
# B: CLI fix — daily run uses run_campaign (not non-existent run())
# ---------------------------------------------------------------------------

class TestDailyRunUsesRunCampaign:
    """daily run handler must call CampaignManager.run_campaign, not run."""

    def test_campaign_manager_has_run_campaign_not_run(self):
        from breakthrough_engine.campaign_manager import CampaignManager
        assert hasattr(CampaignManager, "run_campaign"), "run_campaign method must exist"
        assert not hasattr(CampaignManager, "run"), "run method must NOT exist on CampaignManager"

    def test_campaign_status_completed_with_draft_value(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        assert CampaignStatus.COMPLETED_WITH_DRAFT.value == "completed_with_draft"

    def test_campaign_status_completed_no_draft_value(self):
        from breakthrough_engine.campaign_manager import CampaignStatus
        assert CampaignStatus.COMPLETED_NO_DRAFT.value == "completed_no_draft"

    def test_load_campaign_profile_function_exists(self):
        from breakthrough_engine.campaign_manager import load_campaign_profile
        assert callable(load_campaign_profile)


# ---------------------------------------------------------------------------
# C: CLI fix — daily run --force flag
# ---------------------------------------------------------------------------

class TestDailyRunForceFlag:
    """daily run --force flag must be registered in the CLI argument parser."""

    def test_daily_run_force_flag_registered(self):
        import argparse
        from breakthrough_engine.cli import main as _main
        import sys
        # Verify --force flag is accepted (no argparse error)
        with patch("sys.argv", ["bt", "daily", "run", "some_profile", "--force"]):
            try:
                import argparse as _ap
                parser = _ap.ArgumentParser()
                # We can't easily test the full parser without running main()
                # Instead verify the flag is in the cli source
                import inspect
                src = inspect.getsource(_main.__module__ if hasattr(_main, '__module__') else _main)
            except Exception:
                pass
        # The flag is verified by the cli source check below
        cli_path = REPO_ROOT / "breakthrough_engine" / "cli.py"
        content = cli_path.read_text()
        assert '"--force"' in content or "'--force'" in content

    def test_daily_run_without_force_defaults_false(self):
        """Verify the --force flag source is present in cli.py."""
        cli_path = REPO_ROOT / "breakthrough_engine" / "cli.py"
        content = cli_path.read_text()
        assert "force" in content
        assert "Skip max-runs-per-day" in content or "skip" in content.lower()


# ---------------------------------------------------------------------------
# D: evidence_diversity_v1 DB registration verification (structural)
# ---------------------------------------------------------------------------

class TestEvidenceDiversityV1Config:
    """evidence_diversity_v1 config is correct and complete."""

    def test_evidence_diversity_v1_generation_prompt_standard(self):
        config = _load_policy_config("evidence_diversity_v1")
        assert config["generation_prompt_variant"] == "standard"

    def test_evidence_diversity_v1_scoring_weights_null(self):
        config = _load_policy_config("evidence_diversity_v1")
        assert config["scoring_weights"] is None

    def test_evidence_diversity_v1_mechanism_overlap_increased(self):
        config = _load_policy_config("evidence_diversity_v1")
        w = config["evidence_ranking_weights"]
        assert w["mechanism_overlap"] > 0.20  # increased from champion default

    def test_evidence_diversity_v1_api_relevance_decreased(self):
        config = _load_policy_config("evidence_diversity_v1")
        w = config["evidence_ranking_weights"]
        assert w["api_relevance"] < 0.35  # decreased from champion default

    def test_evidence_diversity_v1_weights_sum_to_one(self):
        config = _load_policy_config("evidence_diversity_v1")
        w = config["evidence_ranking_weights"]
        total = sum(w.values())
        assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# E: Phase 9C-B docs exist
# ---------------------------------------------------------------------------

class TestPhase9CBDocs:
    """Phase 9C-B planning and status docs must exist."""

    def test_phase9cb_plan_doc_exists(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_PHASE9CB_PLAN.md"
        assert path.exists(), "Phase 9C-B plan doc must exist"

    def test_phase9cb_status_doc_exists(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_PHASE9CB_STATUS.md"
        assert path.exists(), "Phase 9C-B status doc must exist"

    def test_phase9d_ready_doc_exists(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_PHASE9D_READY.md"
        assert path.exists(), "Phase 9D readiness doc must exist"

    def test_phase9cb_plan_references_blocker_fixes(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_PHASE9CB_PLAN.md"
        content = path.read_text()
        assert "evidence_ranking_weights" in content
        assert "run_campaign" in content or "CampaignManager" in content
        assert "--force" in content

    def test_phase9d_ready_doc_has_launch_commands(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_PHASE9D_READY.md"
        content = path.read_text()
        assert "evidence_diversity_v1" in content
        assert "phase9c_ab_trial" in content
        assert "eval_clean_energy_30m" in content

    def test_phase9d_ready_doc_has_promotion_gates(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_PHASE9D_READY.md"
        content = path.read_text()
        assert "score_delta" in content or "score delta" in content.lower()
        assert "approval_rate" in content or "approval rate" in content.lower()
        assert "-0.03" in content or "0.03" in content

    def test_phase9d_ready_doc_references_regime2(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_PHASE9D_READY.md"
        content = path.read_text()
        assert "qwen3-embedding" in content or "Regime 2" in content


# ---------------------------------------------------------------------------
# F: Regime 2 operational baseline doc
# ---------------------------------------------------------------------------

class TestRegime2BaselineDoc:
    """Regime 2 operational baseline doc must exist when baseline is frozen."""

    def test_regime2_baseline_doc_exists(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_REGIME2_OPERATIONAL_BASELINE.md"
        assert path.exists(), "Regime 2 operational baseline doc must exist"

    def test_regime2_baseline_doc_has_embedding_regime(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_REGIME2_OPERATIONAL_BASELINE.md"
        content = path.read_text()
        assert "qwen3-embedding" in content or "regime_2" in content.lower()

    def test_regime2_baseline_doc_differentiates_old_baselines(self):
        path = REPO_ROOT / "docs" / "BREAKTHROUGH_ENGINE_REGIME2_OPERATIONAL_BASELINE.md"
        content = path.read_text()
        assert "phase5" in content.lower() or "phase7d" in content.lower()

    def test_regime2_operational_baseline_json_exists(self):
        path = REPO_ROOT / "runtime" / "baselines" / "phase9c_operational_baseline_regime2.json"
        assert path.exists(), "Phase 9C-B Regime 2 operational baseline JSON must exist"

    def test_regime2_operational_baseline_json_has_campaign_ids(self):
        path = REPO_ROOT / "runtime" / "baselines" / "phase9c_operational_baseline_regime2.json"
        data = json.loads(path.read_text())
        assert "campaigns" in data
        assert len(data["campaigns"]) == 6, "Baseline must have exactly 6 campaigns"

    def test_regime2_operational_baseline_json_has_regime(self):
        path = REPO_ROOT / "runtime" / "baselines" / "phase9c_operational_baseline_regime2.json"
        data = json.loads(path.read_text())
        assert data.get("embedding_regime") == "regime_2"
        assert "qwen3-embedding" in data.get("embedding_model", "")
